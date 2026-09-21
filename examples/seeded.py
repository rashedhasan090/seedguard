"""Example: sets seeds before RNG use -- seedguard should pass this file."""

import random

import numpy as np


def main() -> None:
    random.seed(42)
    np.random.seed(42)
    print(random.randint(0, 10))
    print(np.random.randn(2))


if __name__ == "__main__":
    main()
