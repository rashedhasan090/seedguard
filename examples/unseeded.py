"""Example: uses RNG without setting a seed -- seedguard should flag this."""

import random

import numpy as np


def sample_batch(n: int = 4) -> list[int]:
    return [random.randint(0, 100) for _ in range(n)]


def noise(shape=(3, 3)):
    return np.random.randn(*shape)
