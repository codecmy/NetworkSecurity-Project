"""Shared constants for the network-security service.

User-verified verdicts live in their own MongoDB database (separate from the
training dataset) so they can be folded into future retraining without
polluting the training pipeline.
"""

FEEDBACK_DATABASE_NAME: str = "NetworkSecurityFeedback"
FEEDBACK_COLLECTION_NAME: str = "feedback"
