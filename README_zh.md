# osu-tools-py (中文说明)

基于 **[pythonnet](https://pythonnet.github.io/)** 的 **[ppy/osu-tools](https://github.com/ppy/osu-tools)** 高性能 Python 封装库。

本库允许你直接在 Python 中计算 osu! 谱面的 **PP (Performance Points)**、**星级 (Star Ratings)** 以及其他难度属性。它内置了官方编译的 C# DLL (来自 osu!lazer)，确保计算结果与官方游戏算法完全一致。

**功能特性：**
*   🚀 **精准**：直接调用 osu!lazer 的原生 C# 代码进行计算。
*   📦 **开箱即用**：内置预编译 DLL，无需用户自行编译 C# 环境。
*   🖥️ **跨平台**：支持 Windows, Linux, 和 macOS (Intel & Apple Silicon/M1/M2)。
*   🧩 **类型安全**：完整的 Python 类型提示 (Type Hints) 和数据类支持。

## 📋 前置要求

在安装本 Python 包之前，你的系统**必须**安装 .NET 8 Runtime。

*   **[下载 .NET 8.0 Runtime](https://dotnet.microsoft.com/en-us/download/dotnet/8.0)**
*   *注意：你只需要下载 "Run console apps" 版本 (Runtime)，不需要安装 SDK。*

## 📦 安装

```bash
pip install osu-tools-py
```

## 🚀 快速开始

### 1. 计算 osu!stable (现行版) PP

为了得到与 osu! 官网 (Stable) 一致的 PP 数据，你必须遵守**两条规则**：
1.  **在 Mod 列表中添加 "CL" (Classic)**。
2.  **提供一个 `legacy_total_score`** (任意大于 0 的整数)。

```python
from osu_tools import OsuCalculator

# 初始化 (自动加载 .NET 运行时)
calc = OsuCalculator()

# 示例：计算 Standard 模式下 HDDT 的满 PP
result = calc.calculate(
    file_path="beatmaps/12345.osu",
    mode=0,
    # 规则 1: 计算 Stable 数据必须带上 CL
    mods=["HD", "DT", "CL"], 
    acc=100.0,
    # 规则 2: 提供 legacy score 以启用 Stable 的物理/计分逻辑
    legacy_total_score=1000000 
)

if result.is_success:
    print(f"星级: {result.stars:.2f}")
    print(f"PP:   {result.pp:.2f}")
    print(f"瞄准: {result.pp_aim:.2f}")
    print(f"速度: {result.pp_speed:.2f}")
else:
    print(f"错误: {result.error}")
```

### 2. 计算实际成绩 (Replay/API 数据)

如果要计算具体的某个成绩，请传入点击统计数据 (Statistics)。

```python
# 实际成绩的统计数据
stats = {
    'great': 450,
    'ok': 12,
    'meh': 1,
    'miss': 2
}

result = calc.calculate(
    file_path="beatmaps/12345.osu",
    mode=0,
    mods=["HD", "CL"], # 别忘了 CL!
    combo=850,
    statistics=stats,
    legacy_total_score=1000000 # Stable 逻辑必需
)

print(f"实际 PP: {result.pp:.2f}")
print(f"Acc PP: {result.pp_acc:.2f}")
```


### 3. Lazer 模式计算示例
如果你想计算新版 Lazer 计分系统下的 PP (滑条尾计入准确率)：

```python
# Lazer 统计数据示例
lazer_stats = {
    'great': 450,
    'ok': 10,
    'miss': 5,
    'slider_tail_hit': 200, # Lazer 特有字段
    'large_tick_hit': 50    # Lazer 特有字段
}

result = calc.calculate(
    file_path="beatmaps/12345.osu",
    mode=0,
    mods=[], 
    combo=800,
    statistics=lazer_stats,
)
```

### 支持的输入参数

*   **Mods**: 支持字符串列表 `["HD", "DT"]`，字典列表 `[{"acronym": "HD"}]`，或对象列表。
*   **Modes (模式)**:
    *   `0`: osu! (Standard)
    *   `1`: osu!taiko
    *   `2`: osu!catch
    *   `3`: osu!mania

### 返回数据
函数返回一个 `CalculationResult` 数据类对象：

```python
@dataclass
class CalculationResult:
    mode: int
    stars: float
    pp: float
    pp_aim: float        # 瞄准 PP
    pp_speed: float      # 速度 PP
    pp_acc: float        # 准确率 PP
    pp_flashlight: float # 手电筒 PP
    max_combo: int
    error: Optional[str]
    # ...
```

## 🛠️ 从源码构建

如果你想修改 C# 逻辑或自己构建 Wheel 包：

1.  **环境要求**:
    *   Python 3.10+
    *   .NET 8.0 SDK
    *   `uv` (Python 包管理器)

2.  **克隆仓库**:
    ```bash
    git clone --recursive https://github.com/yaowan233/osu-tools-py.git
    cd osu-tools-py
    ```

3.  **构建**:
    本项目使用 GitHub Actions 进行多平台矩阵构建，你也可以在本地构建：
    ```bash
    # 1. 编译 C# DLL
    cd osu-tools/PerformanceCalculator
    dotnet publish -c Release -o ../../src/osu_tools/lib

    # 2. 构建 Python Wheel
    cd ../..
    uv build
    ```

## ⚠️ 常见问题排查

1.  **`RuntimeError: Failed to create a default .NET runtime`**:
    *   请确保你安装了 **.NET 8 Runtime**。
    *   在 Linux/macOS 上，请确保 `dotnet` 命令在 PATH 环境变量中。

2.  **计算出的 PP 比官网低**:
    *   请确认是否在 mods 中添加了 `"CL"`？
    *   请确认是否传入了 `legacy_total_score=1000000`？

## 📄 许可证

本项目基于 MIT 许可证开源。
基于 [ppy/osu-tools](https://github.com/ppy/osu-tools) (MIT) 和 [pythonnet](https://github.com/pythonnet/pythonnet) (MIT)。