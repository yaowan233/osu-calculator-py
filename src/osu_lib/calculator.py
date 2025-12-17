import sys
import os
import math
from pathlib import Path
import warnings


# ================= 库配置与初始化 =================

class OsuEnvironment:
    """管理 .NET 运行时和 DLL 加载的单例类"""
    _initialized = False
    _dll_folder = None

    @classmethod
    def setup(cls, dll_folder_path: str = None, dotnet_root: str = None):
        """
        初始化 .NET 环境和加载 osu! DLL。
        :param dll_folder_path: osu-tools publish 后的文件夹路径
        :param dotnet_root: .NET 8 运行时的路径 (可选)
        """
        if cls._initialized:
            return

        # 1. 设置 DLL 路径
        if dll_folder_path:
            cls._dll_folder = Path(dll_folder_path)
        else:
            # 获取当前脚本所在的目录
            current_dir = Path(__file__).parent.absolute()
            # 假设 DLL 都在同级的 lib 文件夹下
            cls._dll_folder = current_dir / "lib"

        if not cls._dll_folder.exists():
            # 兼容开发环境：如果包内没有，尝试找上一级目录的 compiled_output (本地调试用)
            dev_path = Path("osu-tools/published_output")
            if dev_path.exists():
                cls._dll_folder = dev_path
            else:
                raise FileNotFoundError(f"找不到 DLL 目录: {cls._dll_folder}")

        # 2. 将 DLL 目录加入 sys.path 以便 pythonnet 查找
        sys.path.append(str(cls._dll_folder))

        # 3. 加载 Pythonnet Runtime (CoreCLR)
        try:
            from pythonnet import load
            # 如果尚未加载运行时，尝试加载
            # 注意：如果其他库已经加载了运行时，这里可能会抛出警告或忽略
            try:
                load("coreclr")
            except Exception:
                pass  # 运行时可能已被加载，继续尝试
        except ImportError:
            raise ImportError("请先安装 pythonnet: pip install pythonnet")

        import clr
        import System

        # 4. 加载必要的 DLL 引用
        libs_to_load = [
            "osu.Framework.dll",
            "osu.Game.dll",
            "osu.Game.Rulesets.Osu.dll",
            "osu.Game.Rulesets.Taiko.dll",
            "osu.Game.Rulesets.Catch.dll",
            "osu.Game.Rulesets.Mania.dll",
        ]

        for lib in libs_to_load:
            path = cls._dll_folder / lib
            if path.exists():
                try:
                    # 移除 .dll 后缀进行引用
                    clr.AddReference(str(path).replace('.dll', ''))
                except Exception as e:
                    warnings.warn(f"加载 {lib} 失败: {e}")
            else:
                warnings.warn(f"缺失文件: {lib}")

        cls._initialized = True


# ================= 核心计算类 =================

class OsuCalculator:
    def __init__(self, dll_path=None):
        """
        初始化计算器。如果环境未配置，会自动调用 setup。
        """
        if not OsuEnvironment._initialized:
            OsuEnvironment.setup(dll_path)

        # === 关键：在 DLL 加载后才导入 C# 模块 ===
        # 将 C# 类型保存在 self 中，避免污染全局命名空间，也防止 Import 错误
        import System
        from System.IO import FileStream, FileMode, FileAccess, FileShare
        from System.Collections.Generic import List

        # Beatmap & IO
        from osu.Game.Beatmaps.Formats import LegacyBeatmapDecoder
        from osu.Game.IO import LineBufferedReader
        from osu.Game.Beatmaps import FlatWorkingBeatmap

        # Rulesets
        from osu.Game.Rulesets.Osu import OsuRuleset
        from osu.Game.Rulesets.Taiko import TaikoRuleset
        from osu.Game.Rulesets.Catch import CatchRuleset
        from osu.Game.Rulesets.Mania import ManiaRuleset

        # Mods & Scoring
        from osu.Game.Rulesets.Mods import Mod
        from osu.Game.Scoring import ScoreInfo
        from osu.Game.Rulesets.Scoring import HitResult

        # Difficulty Attributes
        from osu.Game.Rulesets.Osu.Difficulty import OsuDifficultyAttributes
        from osu.Game.Rulesets.Taiko.Difficulty import TaikoDifficultyAttributes
        from osu.Game.Rulesets.Catch.Difficulty import CatchDifficultyAttributes
        from osu.Game.Rulesets.Mania.Difficulty import ManiaDifficultyAttributes

        # Catch Objects
        from osu.Game.Rulesets.Catch.Objects import Fruit, Droplet, TinyDroplet, JuiceStream

        # 保存引用到 self (或者作为模块级缓存，这里为了隔离性放在实例或类中)
        self.System = System
        self.FileStream = FileStream
        self.FileMode = FileMode
        self.FileAccess = FileAccess
        self.FileShare = FileShare
        self.List = List
        self.LegacyBeatmapDecoder = LegacyBeatmapDecoder
        self.LineBufferedReader = LineBufferedReader
        self.FlatWorkingBeatmap = FlatWorkingBeatmap
        self.HitResult = HitResult
        self.ScoreInfo = ScoreInfo
        self.Mod = Mod

        # 难度属性映射
        self.DiffAttrs = {
            0: OsuDifficultyAttributes,
            1: TaikoDifficultyAttributes,
            2: CatchDifficultyAttributes,
            3: ManiaDifficultyAttributes
        }

        # Catch 对象类型
        self.CatchObjects = {
            'Fruit': Fruit,
            'Droplet': Droplet,
            'TinyDroplet': TinyDroplet,
            'JuiceStream': JuiceStream
        }

        # 初始化规则集
        self.rulesets = {
            0: OsuRuleset(),
            1: TaikoRuleset(),
            2: CatchRuleset(),
            3: ManiaRuleset()
        }

    def _parse_mods(self, mod_list, ruleset):
        """将 Python 字符串列表转换为 C# Mod 列表"""
        available_mods = ruleset.CreateAllMods()
        csharp_mods = self.List[self.Mod]()  # 泛型列表初始化

        if not mod_list:
            return csharp_mods

        for m in mod_list:
            # 忽略大小写查找
            found = next((x for x in available_mods if str(x.Acronym).upper() == str(m).upper()), None)
            if found:
                csharp_mods.Add(found)
            else:
                print(f"Warning: Mod '{m}' not found.")
        return csharp_mods

    def _extract_stat(self, stats_obj, attr_name, default=0):
        """安全地从对象或字典中获取属性，用于兼容 Pydantic 和 Dict"""
        if stats_obj is None:
            return default
        # 尝试作为字典获取
        if isinstance(stats_obj, dict):
            return stats_obj.get(attr_name, default)
        # 尝试作为对象属性获取 (Pydantic)
        return getattr(stats_obj, attr_name, default)

    def _has_valid_stats(self, stats_obj):
        """检查统计数据是否包含非零的有效点击数"""
        if not stats_obj:
            return False
        # 检查关键字段是否有大于0的值
        keys = ['great', 'ok', 'meh', 'good', 'perfect', 'miss', 'large_tick_hit']
        for k in keys:
            if self._extract_stat(stats_obj, k) > 0:
                return True
        return False

    # ================= 模拟/填充逻辑更新 =================

    def _sim_osu(self, acc, beatmap, misses, stats_obj=None):
        """Standard: 优先使用 stats_obj，否则根据 acc 模拟"""

        # 1. 如果提供了详细数据，直接使用
        if self._has_valid_stats(stats_obj):
            return {
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),
                self.HitResult.Ok: self._extract_stat(stats_obj, 'ok'),
                self.HitResult.Meh: self._extract_stat(stats_obj, 'meh'),
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss')
            }

        # 2. 否则执行模拟逻辑 (Fallback)
        total = beatmap.HitObjects.Count
        relevant = total - misses
        accuracy = acc / 100.0
        n300, n100, n50 = 0, 0, 0

        if relevant <= 0: return {self.HitResult.Miss: misses}
        rel_acc = accuracy * total / relevant
        rel_acc = max(0.0, min(1.0, rel_acc))

        if rel_acc >= 0.25:
            ratio = math.pow(1 - (rel_acc - 0.25) / 0.75, 2)
            c100 = 6 * relevant * (1 - rel_acc) / (5 * ratio + 4)
            c50 = c100 * ratio
            n100 = int(round(c100))
            n50 = int(round(c100 + c50) - n100)
        elif rel_acc >= 1.0 / 6:
            c100 = 6 * relevant * rel_acc - relevant
            c50 = relevant - c100
            n100 = int(round(c100))
            n50 = int(round(c100 + c50) - n100)
        else:
            c50 = 6 * relevant * rel_acc
            n50 = int(round(c50))
            misses = total - n50
        n300 = total - n100 - n50 - misses

        return {
            self.HitResult.Great: max(0, n300),
            self.HitResult.Ok: max(0, n100),
            self.HitResult.Meh: max(0, n50),
            self.HitResult.Miss: max(0, misses)
        }

    def _sim_taiko(self, acc, beatmap, misses, stats_obj=None):
        """Taiko"""
        if self._has_valid_stats(stats_obj):
            return {
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),
                self.HitResult.Ok: self._extract_stat(stats_obj, 'ok'),  # Taiko 的 Good 通常对应 API 的 Ok
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss')
            }

        # Fallback Simulation
        total = beatmap.HitObjects.Count
        relevant = total - misses
        accuracy = acc / 100.0
        n_great = int(round((2 * accuracy - 1) * relevant))
        n_good = relevant - n_great

        return {
            self.HitResult.Great: max(0, n_great),
            self.HitResult.Ok: max(0, n_good),
            self.HitResult.Miss: max(0, misses)
        }

    def _sim_mania(self, acc, beatmap, misses, score_val, stats_obj=None):
        """Mania"""
        if self._has_valid_stats(stats_obj):
            return {
                self.HitResult.Perfect: self._extract_stat(stats_obj, 'perfect'),
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),
                self.HitResult.Good: self._extract_stat(stats_obj, 'good'),
                self.HitResult.Ok: self._extract_stat(stats_obj, 'ok'),
                self.HitResult.Meh: self._extract_stat(stats_obj, 'meh'),
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss')
            }
        total = beatmap.HitObjects.Count
        relevant = total - misses
        accuracy = acc / 100.0
        n_perfect, n_great, n_good, n_ok, n_meh = 0, 0, 0, 0, 0

        if relevant > 0:
            if accuracy >= 0.96:
                p = 1 - (1 - accuracy) / 0.04
                n_perfect = int(round(p * relevant))
                n_great = relevant - n_perfect
            elif accuracy >= 0.90:
                p = 1 - (0.96 - accuracy) / 0.06
                n_great = int(round(p * relevant))
                n_good = relevant - n_great
            elif accuracy >= 0.80:
                p = 1 - (0.90 - accuracy) / 0.10
                n_good = int(round(p * relevant))
                n_ok = relevant - n_good
            elif accuracy >= 0.60:
                p = 1 - (0.80 - accuracy) / 0.20
                n_ok = int(round(p * relevant))
                n_meh = relevant - n_ok
            else:
                n_meh = relevant

        return {
            self.HitResult.Perfect: max(0, n_perfect),
            self.HitResult.Great: max(0, n_great),
            self.HitResult.Good: max(0, n_good),
            self.HitResult.Ok: max(0, n_ok),
            self.HitResult.Meh: max(0, n_meh),
            self.HitResult.Miss: max(0, misses)
        }

    def _sim_catch(self, acc, beatmap, misses, stats_obj=None):
        """Catch"""
        # 1. 优先读取详细数据
        if self._has_valid_stats(stats_obj):
            # 映射 NewStatistics 到 HitResult
            return {
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),  # Fruits
                self.HitResult.LargeTickHit: self._extract_stat(stats_obj, 'large_tick_hit'),  # Droplets
                self.HitResult.SmallTickHit: self._extract_stat(stats_obj, 'small_tick_hit'),  # Tiny Droplets
                self.HitResult.SmallTickMiss: self._extract_stat(stats_obj, 'small_tick_miss'),
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss')
            }

        # 2. 模拟逻辑
        # ... [这里必须保留原本的 max_fruits 统计和数学反推逻辑] ...
        # 重新统计 Max Values 用于计算
        Fruit = self.CatchObjects['Fruit']
        Droplet = self.CatchObjects['Droplet']
        TinyDroplet = self.CatchObjects['TinyDroplet']
        JuiceStream = self.CatchObjects['JuiceStream']

        max_fruits = 0
        max_droplets_total = 0
        max_tiny_droplets = 0

        for h in beatmap.HitObjects:
            if isinstance(h, Fruit):
                max_fruits += 1
            elif isinstance(h, JuiceStream):
                for n in h.NestedHitObjects:
                    if isinstance(n, TinyDroplet):
                        max_tiny_droplets += 1
                        max_droplets_total += 1
                    elif isinstance(n, Droplet):
                        max_droplets_total += 1
                    elif isinstance(n, Fruit):
                        max_fruits += 1

        max_droplets = max_droplets_total - max_tiny_droplets
        max_combo = max_fruits + max_droplets

        # 简单的模拟实现
        count_droplets = max(0, max_droplets - misses)  # 假设 Miss 都是 Droplet Miss (简化)
        count_fruits = max_fruits  # 假设没 Miss Fruit
        count_tiny = max_tiny_droplets  # 假设全连

        return {
            self.HitResult.Great: count_fruits,
            self.HitResult.LargeTickHit: count_droplets,
            self.HitResult.SmallTickHit: count_tiny,
            self.HitResult.Miss: misses
        }

    def calculate(self, file_path, mode=0, mods=None, acc=100.0, combo=None, misses=0,
                  score_val=None, statistics=None):
        """
        :param statistics: Statistics 对象或字典。如果有值，将忽略 acc/misses 进行计算。
        """
        if mods is None: mods = []
        abs_path = os.path.abspath(file_path)

        if not os.path.exists(abs_path):
            return {"error": f"File not found: {abs_path}"}

        ruleset = self.rulesets.get(mode)
        if not ruleset: return {"error": "Invalid mode"}

        fs = None
        reader = None
        try:
            # 1. Load Beatmap
            fs = self.FileStream(abs_path, self.FileMode.Open, self.FileAccess.Read, self.FileShare.Read)
            reader = self.LineBufferedReader(fs)
            decoder = self.LegacyBeatmapDecoder()
            beatmap = decoder.Decode(reader)

            converter = ruleset.CreateBeatmapConverter(beatmap)
            if converter.CanConvert():
                beatmap = converter.Convert()
            working_beatmap = self.FlatWorkingBeatmap(beatmap)

            # 2. Mods & Difficulty
            csharp_mods = self._parse_mods(mods, ruleset)
            diff_calc = ruleset.CreateDifficultyCalculator(working_beatmap)
            diff_attr = diff_calc.Calculate(csharp_mods)  # 这里省略类型转换代码，同之前

            # 3. Hit Results (关键修改)
            stats = {}

            # 如果 statistics 有效，misses 应该从 statistics 里取，以保持一致性
            effective_misses = misses
            if self._has_valid_stats(statistics):
                effective_misses = self._extract_stat(statistics, 'miss')

            if mode == 0:
                stats = self._sim_osu(acc, beatmap, effective_misses, statistics)
            elif mode == 1:
                stats = self._sim_taiko(acc, beatmap, effective_misses, statistics)
            elif mode == 2:
                stats = self._sim_catch(acc, beatmap, effective_misses, statistics)
            elif mode == 3:
                stats = self._sim_mania(acc, beatmap, effective_misses, score_val, statistics)

            # 4. Construct Score
            score = self.ScoreInfo()
            score.Ruleset = ruleset.RulesetInfo
            score.BeatmapInfo = working_beatmap.BeatmapInfo
            score.Mods = csharp_mods.ToArray()

            # 如果传了 Combo 用传的，否则用满 Combo
            score.MaxCombo = int(combo) if combo is not None else diff_attr.MaxCombo
            score.Accuracy = float(acc) / 100.0

            for result, count in stats.items():
                score.Statistics[result] = count

            # 5. Calculate PP
            perf_calc = ruleset.CreatePerformanceCalculator()
            pp_attr = perf_calc.Calculate(score, diff_attr)

            res = {
                "mode": mode,
                "stars": diff_attr.StarRating,
                "pp": pp_attr.Total,
                "max_combo": diff_attr.MaxCombo,
                # 为了调试方便，可以看到到底用了什么判定
                "stats_used": {str(k): v for k, v in stats.items()}
            }
            return res

        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
        finally:
            if reader: reader.Dispose()
            if fs: fs.Dispose()
