# osu-tools-py

[![PyPI](https://img.shields.io/pypi/v/osu-tools-py)](https://pypi.org/project/osu-tools-py/)
[![License](https://img.shields.io/github/license/yaowan233/osu-tools-py)](LICENSE)

[中文说明](https://github.com/yaowan233/osu-tools-py/blob/main/README_zh.md)

A high-performance Python wrapper for **[ppy/osu-tools](https://github.com/ppy/osu-tools)**, powered by **[pythonnet](https://pythonnet.github.io/)**.

This library allows you to calculate **Performance Points (PP)**, **Star Ratings (SR)**, and other difficulty attributes for osu! beatmaps directly from Python. It embeds the official C# DLLs (compiled from osu!lazer), ensuring results are identical to the official game algorithms.

**Features:**
*   🚀 **Accurate**: Uses the actual C# code from osu!lazer for calculations.
*   📦 **Batteries Included**: Comes with pre-compiled DLLs (no need to compile C# yourself).
*   🖥️ **Cross-Platform**: Supports Windows, Linux, and macOS (Intel & Apple Silicon/M1/M2).
*   🧩 **Type Safe**: Fully typed Python API with data classes.

## 📋 Prerequisites

Before installing the Python package, you **must** have the .NET 8 Runtime installed on your system.

*   **[Download .NET 8.0 Runtime](https://dotnet.microsoft.com/en-us/download/dotnet/8.0)**
*   *Note: You only need the "Run console apps" version (Runtime); the SDK is not required for usage.*

## 📦 Installation

```bash
pip install osu-tools-py
```

## 🚀 Quick Start

### 1. Calculate osu!stable PP

To get PP values that match the official osu! website (osu!stable), you must follow **two rules**:
1.  **Add the "CL" (Classic) mod** to your mod list.
2.  **Provide a `legacy_total_score`** (any value > 0).

```python
from osu_tools import OsuCalculator

# Initialize (loads .NET runtime)
calc = OsuCalculator()

# Example: Calculate Max PP for HDDT on Standard Mode
result = calc.calculate(
    file_path="beatmaps/12345.osu",
    mode=0,
    # Rule 1: Always include "CL" for Stable calculations
    mods=["HD", "DT", "CL"], 
    acc=100.0,
    # Rule 2: Provide a legacy score > 0 to enable Stable physics/scoring
    legacy_total_score=1000000 
)

if result.is_success:
    print(f"Stars: {result.stars:.2f}")
    print(f"PP:    {result.pp:.2f}")
    print(f"Aim:   {result.pp_aim:.2f}")
    print(f"Speed: {result.pp_speed:.2f}")
else:
    print(f"Error: {result.error}")
```

### 2. Calculate Real Score (from Replay/API)

When calculating a specific score for osu!stable, pass the hit statistics and ensure you include the Stable compatibility flags.

```python
# Real stats from a score
stats = {
    'great': 450,
    'ok': 12,
    'meh': 1,
    'miss': 2
}

result = calc.calculate(
    file_path="beatmaps/12345.osu",
    mode=0,
    mods=["HD", "CL"], # Don't forget CL!
    combo=850,
    statistics=stats,
    legacy_total_score=1000000 # Required for Stable logic
)

print(f"Real PP: {result.pp:.2f}")
print(f"Real PPAcc: {result.pp_acc:.2f}") # PP from Accuracy
```


### Lazer Calculation Example
If you want to calculate PP for the Lazer scoring system (where slider tails affect accuracy):

```python
# Lazer calculation example
lazer_stats = {
    'great': 450,
    'ok': 10,
    'miss': 5,
    'slider_tail_hit': 200, # Lazer specific stat
    'large_tick_hit': 50    # Lazer specific stat
}

result = calc.calculate(
    file_path="beatmaps/12345.osu",
    mode=0,
    mods=[], 
    combo=800,
    statistics=lazer_stats,
)
```

### Supported Inputs

*   **Mods**: Supports list of strings `["HD", "DT"]`, list of dicts `[{"acronym": "HD"}]`, or objects.
*   **Modes**:
    *   `0`: osu! (Standard)
    *   `1`: osu!taiko
    *   `2`: osu!catch
    *   `3`: osu!mania

### Return Data
The function returns a `CalculationResult` object:

```python
@dataclass
class CalculationResult:
    mode: int
    stars: float
    pp: float
    pp_aim: float
    pp_speed: float
    pp_acc: float
    pp_flashlight: float
    max_combo: int
    error: Optional[str]
    # ...
```

## 🛠️ Building from Source

If you want to modify the C# logic or build the wheels yourself:

1.  **Requirements**:
    *   Python 3.10+
    *   .NET 8.0 SDK
    *   `uv` (Python package manager)

2.  **Clone**:
    ```bash
    git clone --recursive https://github.com/yaowan233/osu-tools-py.git
    cd osu-tools-py
    ```

3.  **Build**:
    The project uses GitHub Actions for matrix builds (Windows/Linux/macOS), but you can build locally:
    ```bash
    # 1. Compile C# DLLs
    cd osu-tools/PerformanceCalculator
    dotnet publish -c Release -o ../../src/osu_tools/lib

    # 2. Build Python Wheel
    cd ../..
    uv build
    ```

## ⚠️ Troubleshooting

1.  **`RuntimeError: Failed to create a default .NET runtime`**:
    *   Ensure you installed **.NET 8 Runtime**.
    *   On Linux/macOS, ensure `dotnet` is in your PATH.

2.  **PP seems lower than official site**:
    *   Did you add `"CL"` to your mods list?
    *   Did you pass `legacy_total_score=1000000`?

## 📄 License

This project is licensed under the MIT License.
Based on [ppy/osu-tools](https://github.com/ppy/osu-tools) (MIT) and [pythonnet](https://github.com/pythonnet/pythonnet) (MIT).
