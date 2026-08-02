import os
import time
import requests
import re
from typing import Dict, Any, Optional
from flask import current_app

class AIService:
    """Service to interact with NVIDIA NIM APIs and Google Gemini Fallbacks."""

    def __init__(self):
        self.nim_circuit_breaker_until = 0.0
        self.nim_news_cache = {}

    def _get_api_keys(self) -> tuple:
        """Retrieve API keys from current_app config or environment."""
        nim_key = os.environ.get("NVIDIA_NIM_API_KEY")
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if current_app:
            nim_key = current_app.config.get("NVIDIA_NIM_API_KEY", nim_key)
            gemini_key = current_app.config.get("GEMINI_API_KEY", gemini_key)
        return nim_key, gemini_key

    def _call_nim(self, model: str, messages: list, temperature: float = 0.2) -> Optional[dict]:
        """Call NVIDIA NIM API with retries and circuit breaker checks."""
        nim_key, _ = self._get_api_keys()
        if not nim_key:
            return None

        # Check circuit breaker
        if time.time() < self.nim_circuit_breaker_until:
            if current_app:
                current_app.logger.warning("NIM Circuit breaker is active. Skipping NIM.")
            return None

        url = os.environ.get("NVIDIA_NIM_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
        headers = {
            "Authorization": f"Bearer {nim_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        retries = 2
        for attempt in range(retries + 1):
            try:
                if current_app:
                    current_app.logger.info(f"Calling NIM API (model: {model}, attempt: {attempt + 1})")
                
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                
                # Check for rate limit (429)
                if resp.status_code == 429:
                    self.nim_circuit_breaker_until = time.time() + 15.0
                    if current_app:
                        current_app.logger.warning("NIM returned 429. Opening circuit breaker for 15s.")
                    return None
                
                resp.raise_for_status()
                return resp.json()

            except Exception as e:
                if attempt < retries:
                    sleep_time = 2 ** attempt
                    if current_app:
                        current_app.logger.warning(f"NIM request failed: {e}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    if current_app:
                        current_app.logger.error(f"NIM request failed completely after {retries} retries: {e}")
                    # If it failed completely with other network issues, let's open circuit breaker too just in case
                    self.nim_circuit_breaker_until = time.time() + 5.0
                    return None
        return None

    def _call_gemini(self, model: str, prompt: str) -> Optional[str]:
        """Call Google Gemini API as fallback."""
        _, gemini_key = self._get_api_keys()
        if not gemini_key:
            if current_app:
                current_app.logger.error("GEMINI_API_KEY is not configured.")
            return None

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }]
        }

        try:
            if current_app:
                current_app.logger.info(f"Calling Gemini Fallback API (model: {model})")
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text")
            return None
        except Exception as e:
            if current_app:
                current_app.logger.error(f"Gemini API request failed: {e}")
            return None

    def generate_thesis_and_reasoning(self, symbol: str, technicals: dict, financials: list, announcements: list) -> dict:
        """Generate AI Score Breakdown & Thesis with internal reasoning chain."""
        # Build prompt content
        tech_summary = (
            f"Symbol: {symbol}\n"
            f"EP Score: {technicals.get('ep_score', 'N/A')}\n"
            f"Neglect Score: {technicals.get('neglect_score', 'N/A')}\n"
            f"Catalyst Score: {technicals.get('catalyst_score', 'N/A')}\n"
            f"Repricing Score: {technicals.get('repricing_score', 'N/A')}\n"
            f"Market Cap: INR {technicals.get('market_cap_cr', 'N/A')} Crores\n"
            f"Rel Volume: {technicals.get('rel_volume', 'N/A')}x\n"
            f"Close Location: {technicals.get('close_loc', 'N/A')}\n"
            f"Daily Change: {technicals.get('price_change_pct', 'N/A')}%\n"
        )
        
        fin_summary = ""
        for f in financials[:2]:
            fin_summary += (
                f"- Quarter: {f.get('quarter', 'N/A')}, Result Date: {f.get('result_date', 'N/A')}, "
                f"Revenue Growth YoY: {f.get('revenue_yoy_pct', '0') or '0'}%, "
                f"Net Profit Growth YoY: {f.get('net_profit_yoy_pct', '0') or '0'}%\n"
            )
            
        ann_summary = ""
        for a in announcements[:3]:
            ann_summary += (
                f"- Date: {a.get('event_date', 'N/A')}, Event: {a.get('event_type', 'N/A')}, Headline: {a.get('headline', '')[:100]}\n"
            )

        # Base instructions
        instruction = (
            "We need to produce a cohesive AI Score Breakdown & Thesis, exactly 2 to 3 sentences, 50 to 80 words total.\n"
            "Must explain catalyst, ground thesis in scores and growth numbers, style of institutional research note, "
            "plain prose, no markdown, no bold, no asterisks, no lists, and no self-promotional terms.\n"
            "Ground your analysis using the following data:\n\n"
            f"--- TECHNICALS ---\n{tech_summary}\n"
            f"--- QUARTERLY FINANCIALS ---\n{fin_summary}\n"
            f"--- CORPORATE ANNOUNCEMENTS ---\n{ann_summary}\n"
        )

        # 1. Try NIM first
        nim_model = os.environ.get("NVIDIA_NIM_MODEL", "meta/llama-3.1-70b-instruct")
        nim_messages = [
            {"role": "system", "content": "You are a senior institutional equity research analyst. Answer strictly under the provided constraints."},
            {"role": "user", "content": instruction}
        ]

        nim_resp = self._call_nim(nim_model, nim_messages)
        if nim_resp:
            choices = nim_resp.get("choices", [])
            if choices:
                choice = choices[0]
                message = choice.get("message", {})
                thesis = message.get("content", "").strip()
                
                # Extract reasoning chain
                reasoning = (
                    message.get("reasoning_content") or 
                    message.get("thought") or 
                    choice.get("reasoning_content") or 
                    choice.get("thought") or 
                    "Reasoning chain generated by meta/llama-3.1-70b-instruct."
                )
                return {"thesis": thesis, "reasoning": reasoning}

        # 2. Fallback to Gemini
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        gemini_prompt = (
            f"{instruction}\n\n"
            "CRITICAL ADDITIONAL INSTRUCTION FOR LOGGING:\n"
            "Before outputting the 2-3 sentence plain prose thesis, you must provide your detailed step-by-step thinking process "
            "explaining how you arrived at the conclusion. Wrap this step-by-step thinking process inside `<thought>...</thought>` XML tags. "
            "The final 2-3 sentence thesis must be placed outside the `<thought>` tags at the very end of your response.\n"
            "Example response structure:\n"
            "<thought>\n- Analyzing metrics...\n- Synthesis...\n</thought>\n"
            "NPST exhibits strong momentum..."
        )

        gemini_text = self._call_gemini(gemini_model, gemini_prompt)
        if gemini_text:
            # Parse <thought> tags
            thought_match = re.search(r"<thought>(.*?)</thought>", gemini_text, re.DOTALL | re.IGNORECASE)
            reasoning = "Gemini fallback reasoning process."
            if thought_match:
                reasoning = thought_match.group(1).strip()
                # Remove thought tags and reasoning text from thesis
                thesis = re.sub(r"<thought>.*?</thought>", "", gemini_text, flags=re.DOTALL | re.IGNORECASE).strip()
            else:
                thesis = gemini_text.strip()
            return {"thesis": thesis, "reasoning": reasoning}

        # Last resort fallback if both fail
        fallback_thesis = (
            f"The episodic pivot for {symbol} is supported by a catalyst score of {technicals.get('catalyst_score', 'N/A')} "
            f"and a final score of {technicals.get('ep_score', 'N/A')}. Growth numbers and volume metrics suggest "
            "institutional interest is starting to build from historical base support."
        )
        return {
            "thesis": fallback_thesis,
            "reasoning": "Default offline fallback generated due to NIM and Gemini API unavailability."
        }

    def analyze_sentiment(self, text: str) -> dict:
        """Utility endpoint sentiment analysis."""
        prompt = (
            "Analyze the sentiment of the following financial text. "
            "You must return ONLY a clean JSON object with three keys: "
            "\"sentiment\" (which must be exactly \"BULLISH\", \"BEARISH\", or \"NEUTRAL\"), "
            "\"score\" (integer confidence score from 1 to 100), "
            "and \"summary\" (brief 1-2 sentence explanation of drivers).\n"
            "Strictly do not output any markdown code blocks, backticks, or extra wrapping text. Return pure JSON.\n"
            f"Text to analyze: {text}"
        )

        # Try NIM
        nim_model = os.environ.get("NVIDIA_NIM_MODEL_LIGHT", "meta/llama-3.1-70b-instruct")
        nim_messages = [
            {"role": "user", "content": prompt}
        ]
        nim_resp = self._call_nim(nim_model, nim_messages)
        if nim_resp:
            choices = nim_resp.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "").strip()
                try:
                    # Clean up markdown JSON wrapper if present
                    clean_content = re.sub(r"```json|```", "", content).strip()
                    import json
                    return json.loads(clean_content)
                except Exception:
                    pass

        # Try Gemini Fallback
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        gemini_text = self._call_gemini(gemini_model, prompt)
        if gemini_text:
            try:
                clean_content = re.sub(r"```json|```", "", gemini_text).strip()
                import json
                return json.loads(clean_content)
            except Exception:
                pass

        # Fallback response
        return {
            "sentiment": "NEUTRAL",
            "score": 50,
            "summary": "Default fallback summary due to AI service rate limit or configurations."
        }

    def analyze_fundamentals(self, metrics: dict) -> dict:
        """Utility endpoint fundamental analysis."""
        prompt = (
            "Analyze the fundamental valuation, growth, and quality of a company with these metrics:\n"
            f"{metrics}\n\n"
            "You must return ONLY a clean JSON object with three keys: "
            "\"verdict\" (which must be exactly \"VALUE_TRAP\", \"UNDERVALUED\", \"FAIRLY_VALUED\", \"OVERVALUED\", or \"GARP\"), "
            "\"score\" (integer rating from 1 to 100), "
            "and \"summary\" (brief financial explanation of the core valuation thesis).\n"
            "Strictly do not output any markdown code blocks, backticks, or extra wrapping text. Return pure JSON."
        )

        # Try NIM
        nim_model = os.environ.get("NVIDIA_NIM_MODEL_LIGHT", "meta/llama-3.1-70b-instruct")
        nim_messages = [
            {"role": "user", "content": prompt}
        ]
        nim_resp = self._call_nim(nim_model, nim_messages)
        if nim_resp:
            choices = nim_resp.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "").strip()
                try:
                    clean_content = re.sub(r"```json|```", "", content).strip()
                    import json
                    return json.loads(clean_content)
                except Exception:
                    pass

        # Try Gemini Fallback
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        gemini_text = self._call_gemini(gemini_model, prompt)
        if gemini_text:
            try:
                clean_content = re.sub(r"```json|```", "", gemini_text).strip()
                import json
                return json.loads(clean_content)
            except Exception:
                pass

        # Fallback response
        return {
            "verdict": "FAIRLY_VALUED",
            "score": 60,
            "summary": "Default fallback fundamental thesis due to API limits or configurations."
        }

    def analyze_announcement(self, symbol: str, headline: str, pdf_text: Optional[str] = None) -> Optional[dict]:
        """
        Evaluate a corporate announcement using NVIDIA NIM (Llama 3.1 70b) or fallback Gemini.
        Returns a dictionary containing catalyst_score, sentiment, nlp_sentiment_score,
        nlp_category, and summary.
        """
        pdf_context = f'\nAttachment text extract: "{pdf_text}".' if pdf_text else ''
        prompt = (
            f'Evaluate this corporate announcement for {symbol}: "{headline}".{pdf_context}\n\n'
            'Return a JSON strictly with these five keys:\n'
            '1) "catalyst_score" as a float between 0.0 and 1.0 (e.g. 0.85 for strong catalyst, 0.50 for neutral).\n'
            '2) "sentiment" as an integer: 1 for Positive, -1 for Negative, or 0 for Neutral.\n'
            '3) "nlp_sentiment_score" as a float between -1.0 (very negative) and 1.0 (very positive).\n'
            '4) "nlp_category" as a short capitalized string representing category (e.g. "Dividend", "Order Win", "Agreements", "Earnings", "Regulatory", "Acquisition", "Personnel Change", "Other").\n'
            '5) "summary" as a short 1-sentence AI summary of the event based on the headline and attachment.\n\n'
            'Strictly do not output any markdown code blocks, backticks, or extra wrapping text. Return pure JSON.'
        )

        # Try NIM first
        nim_model = os.environ.get("NVIDIA_NIM_MODEL_LIGHT", "meta/llama-3.1-70b-instruct")
        nim_messages = [
            {"role": "user", "content": prompt}
        ]
        nim_resp = self._call_nim(nim_model, nim_messages)
        if nim_resp:
            choices = nim_resp.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "").strip()
                try:
                    clean_content = re.sub(r"```json|```", "", content).strip()
                    import json
                    return json.loads(clean_content)
                except Exception:
                    pass

        # Try Gemini Fallback
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
        gemini_text = self._call_gemini(gemini_model, prompt)
        if gemini_text:
            try:
                clean_content = re.sub(r"```json|```", "", gemini_text).strip()
                import json
                return json.loads(clean_content)
            except Exception:
                pass

        return None

    def callNvidiaNimWithRetry(self, model: str, messages: list, temperature: float = 0.2) -> Optional[dict]:
        """Calls NVIDIA NIM API with exponential backoff retries and circuit breaker checks."""
        return self._call_nim(model, messages, temperature)

    def analyze_news_catalysts(self, symbol: str, articles: list) -> dict:
        """
        Analyze news articles to extract a unified sentiment and catalyst summary.
        Uses NVIDIA NIM with a 5-minute cache and fallback to Gemini.
        """
        symbol = symbol.strip().upper()
        
        # Check cache
        if symbol in self.nim_news_cache:
            entry = self.nim_news_cache[symbol]
            if time.time() - entry["timestamp"] < 300:  # 5 minutes
                if current_app:
                    current_app.logger.info(f"Serving news sentiment from cache for {symbol}")
                return entry["result"]

        # If no articles, return neutral default
        if not articles:
            return {
                "sentiment": "sent-neutral",
                "summary": "No recent articles found to analyze."
            }

        # Take top 5 articles
        top_articles = articles[:5]
        
        # Build prompt
        articles_text = ""
        for idx, art in enumerate(top_articles):
            title = art.get('title', '')
            summary = art.get('summary', '') or ''
            source = art.get('source', '')
            articles_text += f"Article {idx+1}:\nTitle: {title}\nSummary: {summary}\nSource: {source}\n\n"

        prompt = (
            "You are a senior institutional equity research analyst. Analyze the following news articles "
            f"for the stock ticker {symbol} in the Indian stock market. Synthesize the core news and determine "
            "if they act as a positive, neutral, or negative catalyst for the stock.\n\n"
            "Articles:\n"
            f"{articles_text}\n"
            "You must return ONLY a valid JSON object (no markdown, no backticks, no wrap text) containing two keys:\n"
            '1) "sentiment": strictly categorized as "sent-positive", "sent-neutral", or "sent-negative".\n'
            '2) "summary": a synthesized 1-2 sentence explanation of WHY the news acts as a catalyst and its expected impact on the stock.\n\n'
            "Strictly do not output any other text or markdown block formatting. Return pure JSON."
        )

        nim_model = os.environ.get("NVIDIA_NIM_MODEL_LIGHT", "meta/llama-3.1-70b-instruct")
        nim_messages = [
            {"role": "system", "content": "You are a professional financial analyst. Return pure JSON matching the requested schema."},
            {"role": "user", "content": prompt}
        ]

        result = None
        
        # Call NVIDIA NIM with retry wrapper
        try:
            nim_resp = self.callNvidiaNimWithRetry(nim_model, nim_messages)
            if nim_resp:
                choices = nim_resp.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "").strip()
                    # Clean markdown wrappers if returned
                    clean_content = re.sub(r"```json|```", "", content).strip()
                    import json
                    parsed = json.loads(clean_content)
                    if "sentiment" in parsed and "summary" in parsed:
                        # Validate sentiment values
                        if parsed["sentiment"] not in ["sent-positive", "sent-neutral", "sent-negative"]:
                            s = parsed["sentiment"].lower()
                            if "pos" in s or "bull" in s:
                                parsed["sentiment"] = "sent-positive"
                            elif "neg" in s or "bear" in s:
                                parsed["sentiment"] = "sent-negative"
                            else:
                                parsed["sentiment"] = "sent-neutral"
                        result = parsed
        except Exception as e:
            if current_app:
                current_app.logger.warning(f"NIM analysis failed for {symbol}: {e}. Trying Gemini fallback.")

        # Fallback to Gemini if NIM failed
        if not result:
            gemini_model = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
            try:
                gemini_text = self._call_gemini(gemini_model, prompt)
                if gemini_text:
                    clean_content = re.sub(r"```json|```", "", gemini_text).strip()
                    import json
                    parsed = json.loads(clean_content)
                    if "sentiment" in parsed and "summary" in parsed:
                        if parsed["sentiment"] not in ["sent-positive", "sent-neutral", "sent-negative"]:
                            s = parsed["sentiment"].lower()
                            if "pos" in s or "bull" in s:
                                parsed["sentiment"] = "sent-positive"
                            elif "neg" in s or "bear" in s:
                                parsed["sentiment"] = "sent-negative"
                            else:
                                parsed["sentiment"] = "sent-neutral"
                        result = parsed
            except Exception as e:
                if current_app:
                    current_app.logger.error(f"Gemini fallback analysis failed for {symbol}: {e}")

        # Final default fallback if everything fails
        if not result:
            result = {
                "sentiment": "sent-neutral",
                "summary": "Could not determine sentiment due to AI analysis service unavailability."
            }

        # Cache result
        self.nim_news_cache[symbol] = {
            "result": result,
            "timestamp": time.time()
        }

        return result

    def generate_daily_market_brief(self, context: dict) -> Optional[dict]:
        """
        Generate a structured daily pre-market brief via Google Gemini API (gemini-2.5-flash / GEMINI_MODEL).
        Returns a dict matching the requested JSON schema or None if AI is unavailable.
        """
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        
        regime = context.get("regime", {})
        news = context.get("news", [])
        movers = context.get("movers", [])

        news_str = "\n".join([f"- {n.get('title', '')} ({n.get('source', '')}): {n.get('summary', '')}" for n in news[:8]])
        movers_str = "\n".join([f"- {m.get('ticker', '')}: {m.get('setupLabel', 'Breakout')}, Score: {m.get('score', '')}" for m in movers[:6]])

        prompt = (
            "You are an elite Indian market quantitative strategist. Synthesize a pre-market daily brief for NSE India traders.\n\n"
            f"Market Regime Score: {regime.get('score', 50)}/100 ({regime.get('band', 'Neutral')})\n"
            f"Advances/Declines: {regime.get('advances', 0)} / {regime.get('declines', 0)}\n"
            f"Pct Above 21D MA: {regime.get('pct_sma21', 0)}%\n\n"
            f"Top Overnight News/Filings:\n{news_str or 'No major corporate actions.'}\n\n"
            f"Top Momentum Movers (Episodic Pivots / Bull Snort):\n{movers_str or 'None.'}\n\n"
            "Return ONLY a valid JSON object with EXACTLY these keys:\n"
            '1) "headline": a sharp 1-line morning market summary headline.\n'
            '2) "regime_summary": a 2-sentence macro analysis explaining current market breadth and sentiment.\n'
            '3) "sector_catalysts": array of objects `[{"sector": str, "bias": "Bullish"|"Neutral"|"Bearish", "driver": str}]` (max 3 items).\n'
            '4) "actionable_stocks": array of objects `[{"symbol": str, "reason": str}]` (max 4 items).\n'
            '5) "key_risks": array of strings (max 2 items).\n\n'
            "Do NOT include markdown formatting or backticks. Return pure JSON."
        )

        try:
            gemini_text = self._call_gemini(gemini_model, prompt)
            if gemini_text:
                clean_content = re.sub(r"```json|```", "", gemini_text).strip()
                import json
                parsed = json.loads(clean_content)
                if "headline" in parsed and "regime_summary" in parsed:
                    return parsed
        except Exception as e:
            if current_app:
                current_app.logger.warning(f"Gemini Daily Market Brief failed: {e}")

        return None


# Singleton instance
ai_service = AIService()

