# -*- coding: utf-8 -*-
"""Canonical Volcengine Ark model IDs.

This module has no project dependencies so config, credential catalog and the
generation model registry can all import the same literals.
"""
from __future__ import absolute_import

ARK_SEEDREAM_PRO = "doubao-seedream-5-0-pro-260628"
ARK_SEEDREAM_FLASH = "doubao-seedream-5-0-flash-260915"
ARK_SEEDANCE_25 = "doubao-seedance-2-5-260628"
ARK_SEEDANCE_20 = "doubao-seedance-2-0-260128"
ARK_SEEDANCE_10_PRO = "doubao-seedance-1-0-pro-250528"

# Registry key -> official model ID.  These keys are also the model-override
# keys stored in provider_credentials.model_overrides.
ARK_MODEL_IDS = {
    "ark_seedream_pro": ARK_SEEDREAM_PRO,
    "ark_seedream_flash": ARK_SEEDREAM_FLASH,
    "ark_seedance_25": ARK_SEEDANCE_25,
    "ark_seedance_20": ARK_SEEDANCE_20,
    "ark_seedance_10_pro": ARK_SEEDANCE_10_PRO,
}

# Old UI keys map to the canonical model for selection/lookup only.  A legacy
# model override stored under an alias is never applied to the new model.
ARK_MODEL_ALIASES = {
    "ark_seedream_lite": "ark_seedream_flash",
}

ARK_IMAGE_DEFAULT_KEY = "ark_seedream_flash"
ARK_VIDEO_DEFAULT_KEY = "ark_seedance_25"
