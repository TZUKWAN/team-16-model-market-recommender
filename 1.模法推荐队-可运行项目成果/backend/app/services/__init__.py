"""Services layer for the Model Market Assistant.

Import concrete services from their own modules. Keeping this package initializer
side-effect free avoids circular imports between repositories and services.
"""

__all__ = [
    "DemandParser",
    "ModelRecommendationService",
    "CompositionPlanner",
    "load_models",
    "load_eval_sets",
]
