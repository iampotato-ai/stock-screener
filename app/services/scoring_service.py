"""
Momentum Confidence Score Service
Orchestrates the calculation of Momentum Confidence Scores for stocks
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, date
import logging
from config import load_momentum_score_weights, save_momentum_score_weights
from app.extensions import db
from app.models import MomentumScore

# Import scoring modules (will be created)
try:
    from app.services.scoring.technical import TechnicalAnalyzer
    from app.services.scoring.fundamentals import FundamentalAnalyzer
    from app.services.scoring.momentum import MomentumAnalyzer
    from app.services.scoring.institutional import InstitutionalAnalyzer
    from app.services.scoring.risk import RiskAnalyzer
    from app.services.scoring.badges import BadgeAwarder
    from app.services.scoring.explanations import ExplanationGenerator
    from app.services.scoring.ranking import StockRanker
except ImportError as e:
    # Handle case where modules don't exist yet during initial development
    logging.warning(f"Some scoring modules not yet implemented: {e}")
    TechnicalAnalyzer = None
    FundamentalAnalyzer = None
    MomentumAnalyzer = None
    InstitutionalAnalyzer = None
    RiskAnalyzer = None
    BadgeAwarder = None
    ExplanationGenerator = None
    StockRanker = None

logger = logging.getLogger(__name__)

class MomentumConfidenceScoreService:
    """
    Service for calculating and managing Momentum Confidence Scores™
    """

    def __init__(self):
        """Initialize the scoring service with all required components."""
        # Load weights from configuration
        self.weights = load_momentum_score_weights()

        # Initialize analyzers (will be None if modules not yet created)
        self.technical_analyzer = TechnicalAnalyzer() if TechnicalAnalyzer else None
        self.fundamental_analyzer = FundamentalAnalyzer() if FundamentalAnalyzer else None
        self.momentum_analyzer = MomentumAnalyzer() if MomentumAnalyzer else None
        self.institutional_analyzer = InstitutionalAnalyzer() if InstitutionalAnalyzer else None
        self.risk_analyzer = RiskAnalyzer() if RiskAnalyzer else None
        self.badge_awarder = BadgeAwarder() if BadgeAwarder else None
        self.explanation_generator = ExplanationGenerator() if ExplanationGenerator else None
        self.ranking_system = StockRanker() if StockRanker else None

        logger.info(f"MomentumConfidenceScoreService initialized with weights: {self.weights}")

    def calculate_score_for_stock(self, symbol: str, exchange: str = 'NSE',
                                calculation_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Calculate Momentum Confidence Score for a single stock.

        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            exchange: Stock exchange (default: 'NSE')
            calculation_date: Date for calculation (default: today)

        Returns:
            Dictionary containing score breakdown, badges, explanation, and metadata
        """
        if calculation_date is None:
            calculation_date = date.today()

        logger.info(f"Calculating Momentum Confidence Score for {symbol}.{exchange} on {calculation_date}")

        # Initialize result structure
        result = {
            'symbol': symbol,
            'exchange': exchange,
            'date': calculation_date.isoformat(),
            'total_score': 0,
            'pillar_scores': {
                'technical': 0,
                'fundamental': 0,
                'momentum': 0,
                'institutional': 0,
                'risk_liquidity': 0
            },
            'weighted_scores': {
                'technical': 0,
                'fundamental': 0,
                'momentum': 0,
                'institutional': 0,
                'risk_liquidity': 0
            },
            'badges': [],
            'explanation': '',
            'calculated_at': datetime.utcnow().isoformat(),
            'success': False,
            'error': None
        }

        try:
            # Check if all required analyzers are available
            if not all([self.technical_analyzer, self.fundamental_analyzer,
                       self.momentum_analyzer, self.institutional_analyzer,
                       self.risk_analyzer]):
                raise Exception("One or more required analyzers are not available")

            # TODO: In a real implementation, we would fetch actual stock data here
            # For now, we'll use placeholder/mock data to demonstrate the flow
            stock_data = self._get_mock_stock_data(symbol, exchange)

            # Calculate scores for each pillar
            technical_result = self.technical_analyzer.analyze(stock_data)
            fundamental_result = self.fundamental_analyzer.analyze(stock_data)
            momentum_result = self.momentum_analyzer.analyze(stock_data)
            institutional_result = self.institutional_analyzer.analyze(stock_data)
            risk_result = self.risk_analyzer.analyze(stock_data)

            # Extract raw scores (0 to max points for each pillar)
            result['pillar_scores']['technical'] = technical_result.get('score', 0)
            result['pillar_scores']['fundamental'] = fundamental_result.get('score', 0)
            result['pillar_scores']['momentum'] = momentum_result.get('score', 0)
            result['pillar_scores']['institutional'] = institutional_result.get('score', 0)
            result['pillar_scores']['risk_liquidity'] = risk_result.get('score', 0)

            # Apply weights to get weighted contributions
            result['weighted_scores']['technical'] = round(
                result['pillar_scores']['technical'] *
                (self.weights['technical_strength'] / 30.0), 2
            )
            result['weighted_scores']['fundamental'] = round(
                result['pillar_scores']['fundamental'] *
                (self.weights['fundamental_quality'] / 25.0), 2
            )
            result['weighted_scores']['momentum'] = round(
                result['pillar_scores']['momentum'] *
                (self.weights['momentum'] / 20.0), 2
            )
            result['weighted_scores']['institutional'] = round(
                result['pillar_scores']['institutional'] *
                (self.weights['institutional_confidence'] / 15.0), 2
            )
            result['weighted_scores']['risk_liquidity'] = round(
                result['pillar_scores']['risk_liquidity'] *
                (self.weights['risk_liquidity'] / 10.0), 2
            )

            # Calculate total score (sum of weighted scores)
            result['total_score'] = round(
                result['weighted_scores']['technical'] +
                result['weighted_scores']['fundamental'] +
                result['weighted_scores']['momentum'] +
                result['weighted_scores']['institutional'] +
                result['weighted_scores']['risk_liquidity']
            )

            # Collect details for explanation
            result['technical_details'] = technical_result.get('details', {})
            result['fundamental_details'] = fundamental_result.get('details', {})
            result['momentum_details'] = momentum_result.get('details', {})
            result['institutional_details'] = institutional_result.get('details', {})
            result['risk_details'] = risk_result.get('details', {})

            # Generate badges
            if self.badge_awarder:
                result['badges'] = self.badge_awarder.award_badges(result)

            # Generate explanation
            if self.explanation_generator:
                result['explanation'] = self.explanation_generator.generate_explanation(result)

            result['success'] = True

            # Save to database
            self._save_score_to_db(result)

            logger.info(f"Successfully calculated score for {symbol}.{exchange}: {result['total_score']}")

        except Exception as e:
            error_msg = f"Error calculating score for {symbol}.{exchange}: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['success'] = False

        return result

    def _get_mock_stock_data(self, symbol: str, exchange: str) -> Dict[str, Any]:
        """
        Get mock stock data for demonstration purposes.
        In a real implementation, this would fetch actual data from databases/APIs.
        """
        # This is placeholder data - in reality, we'd query our databases
        # for daily bars, fundamentals, corporate events, etc.
        return {
            'symbol': symbol,
            'exchange': exchange,
            # Technical data
            'price': 2500.50,
            'ema_20': 2450.30,
            'ema_50': 2400.80,
            'ema_100': 2350.20,
            'ema_200': 2300.10,
            'rsi': 65.5,
            'macd': 12.5,
            'macd_signal': 10.2,
            'adx': 28.0,
            'supertrend': 2480.0,
            'supertrend_direction': 1,  # 1 for uptrend, -1 for downtrend
            'price_vs_52w_high': 0.85,  # 85% of 52-week high
            'higher_highs': True,
            'higher_lows': True,
            'golden_cross': True,  # 50 EMA > 200 EMA
            # Fundamental data
            'revenue_growth_yoy': 0.18,  # 18%
            'profit_growth_yoy': 0.22,   # 22%
            'roe': 0.25,                 # 25%
            'roce': 0.28,                # 28%
            'debt_to_equity': 0.15,      # 0.15
            'operating_margin': 0.18,    # 18%
            'net_margin': 0.12,          # 12%
            'positive_cash_flow': True,
            'promoter_holding': 0.58,    # 58%
            'promoter_pledge': 0.0,      # 0%
            # Momentum data
            'relative_strength': 78.0,   # RS rating
            'volume_ratio': 2.5,         # 2.5x average volume
            'price_vs_52w_high_pct': 85.0,  # 85% of 52-week high
            'vcp_pattern': False,        # Volatility Contraction Pattern
            'breakout_detected': True,
            'momentum_acceleration': 0.15, # 15% acceleration
            # Institutional data
            'mf_buying': True,           # Mutual Fund buying
            'fii_buying': True,          # FII buying
            'dii_buying': False,         # DII buying
            'promoter_increase': False,  # Promoter holding increase
            'bulk_deals': 2,             # Number of bulk deals
            'block_deals': 1,            # Number of block deals
            # Risk & Liquidity data
            'avg_volume_30d': 1500000,   # 1.5M shares
            'market_cap_cr': 50000,      # Rs. 50,000 crores
            'bid_ask_spread': 0.05,      # 0.05%
            'volatility_30d': 0.25,      # 25% annualized
            'circuit_history': 0,        # No circuit hits in last year
            'operator_risk': 'low'       # Low operator risk
        }

    def _save_score_to_db(self, score_data: Dict[str, Any]) -> None:
        """Save the calculated score to the database."""
        try:
            # Check if score already exists for this stock/date
            from datetime import datetime
            calculation_date = datetime.strptime(score_data['date'], '%Y-%m-%d').date()
            existing = MomentumScore.query.filter_by(
                symbol=score_data['symbol'],
                exchange=score_data['exchange'],
                date=calculation_date
            ).first()

            if existing:
                # Update existing record
                existing.total_score = score_data['total_score']
                existing.technical_score = score_data['pillar_scores']['technical']
                existing.fundamental_score = score_data['pillar_scores']['fundamental']
                existing.momentum_score = score_data['pillar_scores']['momentum']
                existing.institutional_score = score_data['pillar_scores']['institutional']
                existing.risk_liquidity_score = score_data['pillar_scores']['risk_liquidity']
                existing.badges = score_data['badges']
                existing.calculated_at = datetime.utcnow()
            else:
                # Create new record
                new_score = MomentumScore(
                    symbol=score_data['symbol'],
                    exchange=score_data['exchange'],
                    date=calculation_date,
                    total_score=score_data['total_score'],
                    technical_score=score_data['pillar_scores']['technical'],
                    fundamental_score=score_data['pillar_scores']['fundamental'],
                    momentum_score=score_data['pillar_scores']['momentum'],
                    institutional_score=score_data['pillar_scores']['institutional'],
                    risk_liquidity_score=score_data['pillar_scores']['risk_liquidity'],
                    badges=score_data['badges']
                )
                db.session.add(new_score)

            db.session.commit()
            logger.debug(f"Saved score for {score_data['symbol']} to database")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving score to database: {e}")
            raise

    def get_latest_score(self, symbol: str, exchange: str = 'NSE') -> Optional[Dict[str, Any]]:
        """
        Get the latest calculated score for a stock.

        Args:
            symbol: Stock symbol
            exchange: Stock exchange

        Returns:
            Dictionary with score data or None if not found
        """
        try:
            score_record = MomentumScore.query.filter_by(
                symbol=symbol,
                exchange=exchange
            ).order_by(MomentumScore.date.desc()).first()

            if score_record:
                return score_record.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error retrieving score for {symbol}.{exchange}: {e}")
            return None

    def get_top_stocks(self, limit: int = 50, exchange: str = 'NSE') -> List[Dict[str, Any]]:
        """
        Get top scoring stocks.

        Args:
            limit: Maximum number of stocks to return
            exchange: Stock exchange to filter by

        Returns:
            List of stock score dictionaries ordered by score descending
        """
        try:
            scores = MomentumScore.query.filter_by(
                exchange=exchange
            ).order_by(
                MomentumScore.total_score.desc()
            ).limit(limit).all()

            return [score.to_dict() for score in scores]
        except Exception as e:
            logger.error(f"Error retrieving top stocks: {e}")
            return []

    def get_daily_ranking(self, exchange: str = 'NSE') -> Dict[str, Any]:
        """
        Get a daily ranking report for all stocks on the specified exchange.

        Args:
            exchange: Stock exchange to filter by (default: 'NSE')

        Returns:
            Dictionary containing ranking statistics and top stocks
        """
        try:
            from datetime import date

            # Get all scores for today
            today = date.today()
            scores = MomentumScore.query.filter_by(
                exchange=exchange,
                date=today
            ).order_by(
                MomentumScore.total_score.desc()
            ).all()

            if not scores:
                return {
                    'date': today.isoformat(),
                    'exchange': exchange,
                    'total_stocks': 0,
                    'ranked_stocks': 0,
                    'average_score': 0,
                    'top_stocks': [],
                    'score_distribution': {}
                }

            # Convert to dictionary format
            score_dicts = [score.to_dict() for score in scores]

            # Calculate statistics
            total_stocks = len(score_dicts)
            ranked_stocks = len([s for s in score_dicts if s.get('total_score') is not None])

            if ranked_stocks > 0:
                average_score = sum(s.get('total_score', 0) for s in score_dicts) / ranked_stocks
            else:
                average_score = 0

            # Get top 10 stocks
            top_stocks = score_dicts[:10]

            # Score distribution
            distribution = {
                '95-100': len([s for s in score_dicts if 95 <= s.get('total_score', 0) <= 100]),
                '90-94': len([s for s in score_dicts if 90 <= s.get('total_score', 0) <= 94]),
                '80-89': len([s for s in score_dicts if 80 <= s.get('total_score', 0) <= 89]),
                '70-79': len([s for s in score_dicts if 70 <= s.get('total_score', 0) <= 79]),
                '60-69': len([s for s in score_dicts if 60 <= s.get('total_score', 0) <= 69]),
                '0-59': len([s for s in score_dicts if 0 <= s.get('total_score', 0) <= 59])
            }

            return {
                'date': today.isoformat(),
                'exchange': exchange,
                'total_stocks': total_stocks,
                'ranked_stocks': ranked_stocks,
                'average_score': round(average_score, 2),
                'top_stocks': top_stocks,
                'score_distribution': distribution
            }
        except Exception as e:
            logger.error(f"Error generating daily ranking: {e}")
            return {
                'date': date.today().isoformat(),
                'exchange': exchange,
                'error': str(e)
            }