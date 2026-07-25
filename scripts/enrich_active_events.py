import os
import sys
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Include current directory in python path
sys.path.append(os.getcwd())

load_dotenv()

from app import create_app
app = create_app()
app.testing = True

with app.app_context():
    from app.services.nlp_service import nlp_service
    from app.utils.helpers import fetch_announcement_content
    
    conn = sqlite3.connect('scan_history.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # 1. Fetch active symbols
    c.execute('SELECT DISTINCT symbol FROM ep_features WHERE feature_date = (SELECT MAX(feature_date) FROM ep_features)')
    active_feat = [r[0] for r in c.fetchall()]
    
    c.execute('SELECT DISTINCT symbol FROM ep_watchlist WHERE status = "ACTIVE"')
    active_wl = [r[0] for r in c.fetchall()]
    
    active_symbols = list(set(active_feat + active_wl))
    print(f"Found {len(active_symbols)} active symbols in features and watchlist.")
    
    if not active_symbols:
        print("No active symbols found.")
        sys.exit(0)
        
    # 2. Fetch un-enriched events from the last 30 days
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    placeholders = ','.join(['?'] * len(active_symbols))
    query = f'''
        SELECT id, symbol, event_date, headline, raw_url
        FROM corporate_events
        WHERE symbol IN ({placeholders})
          AND event_date >= ?
          AND (summary IS NULL OR summary = "" OR summary = headline)
        ORDER BY event_date DESC
    '''
    c.execute(query, active_symbols + [thirty_days_ago])
    events = [dict(r) for r in c.fetchall()]
    print(f"Found {len(events)} events requiring enrichment.")
    
    # 3. Process each event
    enriched_count = 0
    for ev in events:
        ev_id = ev['id']
        symbol = ev['symbol']
        headline = ev['headline']
        raw_url = ev['raw_url']
        event_date = ev['event_date']
        
        print(f"\n[{enriched_count+1}/{len(events)}] Enriching {symbol} ({event_date}): {headline}")
        
        # Download and parse PDF attachment if available
        pdf_text = ""
        if raw_url:
            try:
                print(f"  Downloading PDF: {raw_url}")
                pdf_text = fetch_announcement_content(raw_url) or ""
                print(f"  Extracted {len(pdf_text)} chars.")
            except Exception as ex:
                print(f"  Failed to fetch PDF content: {ex}")
                
        # Run classification
        try:
            res = nlp_service.process_announcement(headline, pdf_text, raw_url, symbol)
            cat = res['cat']
            
            # Map cat to event_type
            if cat == "cat-order-win":
                event_type_mapped = "ORDER_WIN"
            elif cat == "cat-capex":
                event_type_mapped = "CAPEX_EXPANSION"
            elif cat == "cat-governance":
                event_type_mapped = "MGMT_CHANGE"
            elif cat == "cat-regulatory":
                if res.get('sentiment') == -1:
                    event_type_mapped = "FRAUD_CONCERN"
                else:
                    event_type_mapped = "UNKNOWN"
            else:
                event_type_mapped = "UNKNOWN"
                
            sent_val = res['sentiment']
            cat_score = res['catalyst_score']
            summary = res['summary']
            
            # Update database row
            c.execute('''
                UPDATE corporate_events SET
                    event_type = ?, sentiment = ?, catalyst_score = ?,
                    nlp_sentiment_score = ?, nlp_category = ?, summary = ?,
                    impact_magnitude = ?
                WHERE id = ?
            ''', (
                event_type_mapped, sent_val, cat_score,
                res['nlp_sentiment_score'], res['nlp_category'],
                summary, res['impact_magnitude'], ev_id
            ))
            conn.commit()
            print(f"  Success: category={res['nlp_category']}, score={cat_score}, summary={summary[:80]}...")
            enriched_count += 1
            
        except Exception as ex:
            print(f"  Failed to classify: {ex}")
            
    conn.close()
    print(f"\nCompleted! Enriched {enriched_count} corporate events.")
