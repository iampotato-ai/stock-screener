# Corporate Events NLP Enhancement Plan

## Overview
This document outlines the enhancement plan for the Corporate Events & Announcements feature in MomentumScan. Currently, corporate events are processed using basic keyword matching which limits the system's ability to truly "read and understand" announcements. This enhancement leverages Natural Language Processing (NLP) techniques to provide deeper analysis of corporate announcements, resulting in more accurate sentiment analysis, better event categorization, and improved catalyst scoring for the Episodic Pivot (EP) system.

## Current Limitations

1. **Basic Classification**: Relies on simple keyword matching in `classify_announcement()` function
2. **Surface-Level Understanding**: Stores headline and metadata but doesn't analyze announcement content deeply
3. **Static Scoring**: Uses predefined `EP_CATALYST_BASE` scores without considering context or nuance
4. **Limited Sentiment Analysis**: Only positive/negative/neutral classification without confidence scores
5. **No Content Summarization**: Long announcements are not summarized for quick consumption

## Proposed Solution

Implement an NLP-enhanced announcement processing pipeline that:
1. Fetches full announcement content when available
2. Uses transformer models for sentiment analysis, categorization, and summarization
3. Stores enhanced metadata in the database
4. Provides richer information in the UI
5. Maintains backward compatibility with fallback to existing methods

## Implementation Details

### 1. Required Dependencies
Add to `requirements.txt`:
```
transformers>=4.30.0
torch>=2.0.0
```

### 2. Database Schema Enhancement
Add new columns to `corporate_events` table:
```sql
ALTER TABLE corporate_events ADD COLUMN nlp_sentiment_score REAL;
ALTER TABLE corporate_events ADD COLUMN nlp_category TEXT;
ALTER TABLE corporate_events ADD COLUMN summary TEXT;
ALTER TABLE corporate_events ADD COLUMN impact_magnitude REAL;
```

### 3. Code Changes

#### A. NLP Model Initialization (app.py)
```python
# Add imports
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM, AutoModelForSequenceClassification
import torch

# Initialize NLP models (after other global initializations)
try:
    # Financial sentiment analysis model
    sentiment_analyzer = pipeline(
        "sentiment-analysis",
        model="ProsusAI/finbert",  # Financial BERT for better financial sentiment
        tokenizer="ProsusAI/finbert",
        return_all_scores=True
    )
    
    # Summarization model for long announcements
    summarizer = pipeline(
        "summarization",
        model="facebook/bart-large-cnn",
        device=0 if torch.cuda.is_available() else -1
    )
    
    # Zero-shot classifier for event categorization
    event_classifier = pipeline(
        "zero-shot-classification",
        model="facebook/bart-large-mnli"
    )
    
    NLP_AVAILABLE = True
except Exception as e:
    print(f"Warning: Could not load NLP models: {e}")
    NLP_AVAILABLE = False
    sentiment_analyzer = summarizer = event_classifier = None
```

#### B. Enhanced Announcement Processing Function
```python
def enhanced_classify_announcement(desc, text, raw_url=None):
    """
    Enhanced announcement classification using NLP when available,
    falling back to keyword matching when NLP is not available.
    """
    # Combine available text sources
    full_text = ""
    if desc:
        full_text += desc + " "
    if text:
        full_text += text
    
    # If we have a URL and can fetch content, get the full announcement
    if raw_url and NLP_AVAILABLE:
        try:
            # Fetch and extract text from the announcement URL
            # (Implement fetch_announcement_content or use existing news fetchers)
            full_text = fetch_announcement_content(raw_url) or full_text
        except:
            pass  # Fall back to available text
    
    # Use NLP if available and we have sufficient text
    if NLP_AVAILABLE and len(full_text.strip()) > 50:
        try:
            # Sentiment analysis with financial BERT
            sentiment_results = sentiment_analyzer(full_text[:512])  # Limit length
            # Convert to our format: positive=1, negative=-1, neutral=0
            sentiment_map = {'LABEL_0': -1, 'LABEL_1': 0, 'LABEL_2': 1}  # negative, neutral, positive
            sentiment_score = 0
            sentiment_label = "neutral"
            max_score = 0
            for result in sentiment_results[0]:
                if result['score'] > max_score:
                    max_score = result['score']
                    sentiment_label = result['label']
                    sentiment_score = sentiment_map.get(result['label'], 0)
            
            # Event categorization using zero-shot classification
            event_labels = [
                "financial results", "dividend announcement", "order win", 
                "acquisition", "capex expansion", "management change", 
                "regulatory issue", "bonus issue", "stock split", 
                "analyst upgrade", "analyst downgrade", "guidance raise",
                "guidance cut", "contract win", "plant inauguration"
            ]
            classification = event_classifier(full_text[:1024], event_labels)
            event_category = classification['labels'][0]  # Top label
            category_confidence = classification['scores'][0]
            
            # Generate summary if text is long
            summary = None
            if len(full_text) > 200:
                try:
                    summary_result = summarizer(full_text[:1024], max_length=100, min_length=30, do_sample=False)
                    summary = summary_result[0]['summary_text']
                except:
                    pass
            
            # Calculate enhanced catalyst score based on NLP insights
            base_catalyst = calculate_base_catalyst_from_nlp(sentiment_label, event_category, category_confidence)
            
            return {
                'category': event_category,
                'category_name': event_category.title(),
                'impact': 'earnings-st' if 'result' in event_category.lower() or 'earnings' in event_category.lower() else 'sentiment',
                'impact_name': 'Earnings impact (short-term)' if 'result' in event_category.lower() or 'earnings' in event_category.lower() else 'Sentiment only',
                'sentiment': f"sent-{sentiment_label}",
                'sentiment_name': get_sentiment_emoji(sentiment_label),
                'reason': f"NLP analysis of announcement: {summary or full_text[:200]}...",
                'sentiment_score': sentiment_score,  # -1, 0, 1
                'nlp_sentiment_confidence': max_score,
                'event_category': event_category,
                'category_confidence': category_confidence,
                'summary': summary,
                'enhanced_catalyst_score': base_catalyst
            }
        except Exception as e:
            print(f"NLP analysis failed: {e}, falling back to keyword matching")
            # Fall back to original method
    
    # Fall back to original keyword-based classification
    return classify_announcement(desc, text)  # Original function
```

#### C. Enhanced Catalyst Score Calculation
```python
def calculate_base_catalyst_from_nlp(sentiment_label, event_category, confidence):
    """
    Calculate catalyst score based on NLP analysis results.
    """
    # Base scores by event type (enhanced from EP_CATALYST_BASE)
    event_base_scores = {
        'financial results': 0.60,
        'dividend announcement': 0.40,
        'order win': 0.65,
        'acquisition': 0.55,
        'capex expansion': 0.45,
        'management change': 0.50,
        'regulatory issue': -0.30,
        'bonus issue': 0.25,
        'stock split': 0.20,
        'analyst upgrade': 0.40,
        'analyst downgrade': -0.40,
        'guidance raise': 0.50,
        'guidance cut': -0.70,
        'contract win': 0.60,
        'plant inauguration': 0.35
    }
    
    base_score = event_base_scores.get(event_category.lower(), 0.20)
    
    # Adjust based on sentiment and confidence
    sentiment_multiplier = {
        'positive': 1.2,
        'neutral': 1.0,
        'negative': 0.8
    }.get(sentiment_label, 1.0)
    
    # Apply confidence weighting
    final_score = base_score * sentiment_multiplier * confidence
    
    # Clamp to reasonable range
    return max(-1.0, min(1.0, final_score))
```

#### D. Update Corporate Events Storage
Modify the corporate events insertion code (around lines 1754-1763):
```python
# Get enhanced classification
enhanced_class = enhanced_classify_announcement(desc, text, item.get("attchmntFile", ""))

# Use enhanced data for storage
c.execute('''
    INSERT INTO corporate_events (
        symbol, exchange, event_date, event_type, headline, sentiment,
        catalyst_score, source, raw_url, nlp_sentiment_score, 
        nlp_category, summary, impact_magnitude
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
''', (
    s['ticker'], s['exchange'], date_str, 
    enhanced_class.get('event_type_mapped', event_type_mapped),  # Keep original mapping for compatibility
    desc if desc else text[:200], 
    enhanced_class.get('sentiment', sent_val),  # Keep original sentiment int for compatibility
    enhanced_class.get('enhanced_catalyst_score', cat_score),  # Use enhanced score
    'NSE',
    item.get("attchmntFile", ""),
    enhanced_class.get('sentiment_score', 0),  # NLP sentiment score
    enhanced_class.get('event_category', 'UNKNOWN'),  # NLP category
    enhanced_class.get('summary', None),  # Summary
    abs(enhanced_class.get('enhanced_catalyst_score', cat_score))  # Impact magnitude
))
```

#### E. Frontend Enhancement (static/js/app.js)
Update the corporate events display (around line 11213):
```javascript
// In the corporate events mapping:
eventsContainer.innerHTML = data.corporate_events.map(ev => {
    const sentClass = ev.sentiment === 1 ? 'sent-positive' : ev.sentiment === -1 ? 'sent-negative' : 'sent-neutral';
    const sentText = ev.sentiment === 1 ? '🟢 Positive' : ev.sentiment === -1 ? '🔴 Negative' : '🟡 Neutral';
    
    // Use NLP sentiment if available, otherwise fallback
    const nlpSentiment = ev.nlp_sentiment_score !== null && ev.nlp_sentiment_score !== undefined 
        ? ev.nlp_sentiment_score.toFixed(2) 
        : (ev.sentiment === 1 ? '0.60' : ev.sentiment === -1 ? '-0.60' : '0.00');
    
    const score = ev.catalyst_score ? ev.catalyst_score.toFixed(2) : '-';
    const enhancedScore = ev.enhanced_catalyst_score ? ev.enhanced_catalyst_score.toFixed(2) : score;
    
    return `
        <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.04); border-radius: 6px; padding: 0.8rem; display: flex; flex-direction: column; gap: 0.4rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.75rem;">
                <span style="font-weight:700; color:var(--color-text-muted);">${ev.event_date}</span>
                <div style="display:flex; gap:0.5rem; align-items:center;">
                    <span class="badge" style="background: rgba(255,255,255,0.06); font-size:0.7rem; padding: 1px 4px;">${ev.event_type}</span>
                    <span class="sentiment-badge ${sentClass}" style="font-size:0.7rem; padding: 1px 4px;">${sentText}</span>
                    <span style="font-weight:600; color:var(--accent-blue);">Cat Score: ${score}</span>
                    ${ev.enhanced_catalyst_score !== null && ev.enhanced_catalyst_score !== undefined ? 
                        `<span style="font-weight:600; color:var(--accent-green, #10b981);">NLP Score: ${enhancedScore}</span>` : ''}
                </div>
            </div>
            <div style="font-size:0.8rem; color:#fff; line-height:1.4;">${ev.headline || '-'}</div>
            ${ev.summary ? `<div style="font-size:0.75rem; color:var(--color-text-secondary); font-style:italic; margin-top:0.3rem;">${ev.summary}</div>` : ''}
            ${ev.raw_url ? `<a href="${ev.raw_url}" target="_blank" style="font-size:0.7rem; color:var(--accent-blue); text-decoration:none; align-self:flex-start;">🔗 View Attachment</a>` : ''}
        </div>
    `;
}).join('');
```

## Benefits

1. **Deeper Understanding**: Moves beyond keyword matching to actual content analysis
2. **More Accurate Sentiment**: Financial BERT provides sentiment scores specifically tuned for financial text
3. **Better Categorization**: Zero-shot classification identifies event types without relying on predefined keyword lists
4. **Contextual Scoring**: Catalyst scores are adjusted based on actual content and context
5. **Summarization**: Long announcements are summarized for quick consumption in the UI
6. **Fallback Safety**: If NLP models fail or are unavailable, system falls back to existing keyword-based approach
7. **Enhanced User Experience**: Users see summaries, NLP scores, and more detailed categorization

## Implementation Considerations

1. **Performance**: NLP models add processing time. Mitigation strategies:
   - Process announcements asynchronously
   - Cache results for recently processed announcements
   - Only process announcements that don't already have NLP analysis
   - Consider batch processing during off-peak hours

2. **Model Selection**: 
   - ProsusAI/finbert: Specifically trained on financial text for sentiment analysis
   - facebook/bart-large-cnn: Effective for summarization tasks
   - facebook/bart-large-mnli: Strong zero-shot classification capabilities
   - These can be customized based on performance testing and specific requirements

3. **Hardware Requirements**: 
   - Models will work on CPU but will be significantly faster with GPU acceleration
   - Consider model quantization for deployment on resource-constrained environments

4. **Privacy**: 
   - All processing happens locally (no external API calls for NLP analysis)
   - No privacy concerns with announcement data as it remains within the system

## Testing Strategy

1. **Unit Tests**: Test NLP functions with various announcement types
2. **Integration Tests**: Verify end-to-end flow from announcement fetch to storage and display
3. **Performance Tests**: Measure impact on processing time and optimize as needed
4. **Accuracy Validation**: Compare NLP-enhanced results against manual analysis for sample announcements
5. **Backward Compatibility**: Ensure existing functionality remains intact when NLP is unavailable

## Future Enhancements

1. **Custom Model Training**: Train domain-specific models on Indian corporate announcements
2. **Multi-language Support**: Add support for Hindi and other regional language announcements
3. **Event Relationship Mapping**: Identify related events (e.g., follow-up announcements)
4. **Predictive Scoring**: Use historical data to predict market impact of similar events
5. **Real-time Processing**: Implement streaming processing for live announcement feeds

## Files to Modify

1. `app.py` - Core logic enhancements
2. `requirements.txt` - Add NLP dependencies
3. `static/js/app.js` - UI enhancements for displaying NLP-enhanced data
4. Database migration script - Add new columns to corporate_events table
5. Documentation - Update any relevant documentation

## Conclusion

This enhancement transforms the corporate events feature from a basic keyword-matching system to an intelligent news analysis system that truly "reads and understands" announcements. By leveraging NLP techniques, MomentumScan will provide more accurate, nuanced, and actionable insights from corporate announcements, leading to improved EP scoring and better investment decision-making capabilities.