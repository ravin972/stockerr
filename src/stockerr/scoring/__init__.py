"""AI Confidence Scoring Engine.

Scores each stock 0-100 as a *systematic screen*:

    Confidence = Fundamental x0.50 + Technical x0.30 + Sentiment x0.20

Each sub-score is normalized to 0-100. If a sub-score's data is unavailable, the
remaining weights are renormalized so the confidence stays comparable, and the
gap is noted. A score is decision support, NOT investment advice or a guarantee.
"""

W_FUNDAMENTAL = 0.50
W_TECHNICAL = 0.30
W_SENTIMENT = 0.20
