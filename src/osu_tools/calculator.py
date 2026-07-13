import sys
import os
import math
import warnings
import subprocess
import shutil
from collections import OrderedDict
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Union, Optional, Any, Type, Sequence, Tuple


# ================= 数据结构定义 =================

@dataclass
class CalculationResult:
    """
    计算结果的数据类
    """
    mode: int = 0
    stars: float = 0.0
    pp: float = 0.0
    pp_aim: float = 0.0
    pp_speed: float = 0.0
    pp_acc: float = 0.0
    pp_flashlight: float = 0.0
    max_combo: int = 0
    stats_used: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None


@dataclass
class CalculationRequest:
    """
    单次计算请求。用于 calculate_many；字段与 calculate 参数保持一致。
    """
    file_path: str
    mode: int = 0
    mods: Optional[List[Union[str, Dict[str, Any], Any]]] = None
    acc: float = 100.0
    combo: Optional[int] = None
    misses: int = 0
    legacy_total_score: Optional[int] = None
    statistics: Optional[Union[Dict[str, int], Any]] = None


# ================= 库配置与初始化 =================

class OsuEnvironment:
    """管理 .NET 运行时和 DLL 加载的单例类"""
    _initialized: bool = False

    @classmethod
    def _check_dotnet_installed(cls) -> None:
        """检查系统是否安装了 .NET 8 Runtime"""

        # 1. 检查 dotnet 命令
        # shutil.which 在 Python < 3.12 的 Windows 上不支持 Path 对象，强制转 str
        dotnet_cmd = "dotnet"
        if not shutil.which(str(dotnet_cmd)):
            # Windows fallback check
            if os.name == 'nt':
                program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
                default_path = Path(program_files) / "dotnet" / "dotnet.exe"
                if default_path.exists():
                    dotnet_cmd = str(default_path)
                else:
                    cls._raise_dotnet_error()
            else:
                cls._raise_dotnet_error()

        # 2. 检查 Runtime 版本
        try:
            # Windows 上隐藏 cmd 窗口
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(
                [dotnet_cmd, "--list-runtimes"],
                capture_output=True,
                text=True,
                check=True,
                startupinfo=startupinfo
            )

            if "Microsoft.NETCore.App 8." not in result.stdout:
                raise RuntimeError(
                    f"【版本错误】未检测到 .NET 8 Runtime。\n当前列表:\n{result.stdout}\n"
                    "请下载安装: https://dotnet.microsoft.com/en-us/download/dotnet/8.0"
                )

        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("无法执行 dotnet 命令，请检查 .NET 8 是否正确安装。")

    @staticmethod
    def _raise_dotnet_error():
        raise RuntimeError(
            "【致命错误】未检测到 'dotnet' 命令。\n"
            "请安装 .NET 8 Runtime: https://dotnet.microsoft.com/en-us/download/dotnet/8.0"
        )

    @classmethod
    def setup(cls) -> None:
        if cls._initialized: return

        cls._check_dotnet_installed()

        # 1. 定位 DLL 目录 (合并了你原本代码中的重复逻辑)
        current_dir = Path(__file__).parent.absolute()
        local_lib = current_dir / "lib"
        # 假设结构: src/osu_tools/calculator.py -> osu-tools/published_output
        dev_lib = current_dir.parent.parent / "osu-tools" / "published_output"

        dll_folder: Path

        # 优先使用包内 lib，其次尝试开发目录，最后回退到 local_lib 报错
        if (local_lib / "osu.Game.dll").exists():
            dll_folder = local_lib
        elif (dev_lib / "osu.Game.dll").exists():
            dll_folder = dev_lib
            print(f"DEBUG: 使用开发环境运行库: {dll_folder}")
        else:
            dll_folder = local_lib
            warnings.warn(f"Warning: 核心 DLL 未在 {local_lib} 找到，功能可能失效。")

        if str(dll_folder) not in sys.path:
            sys.path.append(str(dll_folder))

        # 2. 加载运行时
        try:
            from pythonnet import load
            try:
                load("coreclr")
            except Exception as e:
                # 再次尝试或报错
                if "already loaded" not in str(e):
                    raise RuntimeError(f"Pythonnet 加载 CoreCLR 失败: {e}")
        except ImportError:
            raise ImportError("Missing dependency: pythonnet")

        import clr
        import System  # noqa: F401

        # 3. 加载 DLL
        libs_to_load = [
            "osu.Framework.dll",
            "osu.Game.dll",
            "osu.Game.Rulesets.Osu.dll",
            "osu.Game.Rulesets.Taiko.dll",
            "osu.Game.Rulesets.Catch.dll",
            "osu.Game.Rulesets.Mania.dll",
        ]

        for lib in libs_to_load:
            path = dll_folder / lib
            if path.exists():
                try:
                    clr.AddReference(str(path).replace('.dll', ''))
                except Exception:
                    pass  # 忽略已加载或依赖错误
            else:
                pass  # 静默失败，calculate 时会报错

        cls._initialized = True


# ================= 核心计算类 =================

class OsuCalculator:
    def __init__(self, prepared_cache_size: int = 0):
        """
        初始化计算器。如果环境未配置，会自动调用 setup。
        """
        if not OsuEnvironment._initialized:
            OsuEnvironment.setup()

        # 延迟导入 C# 类型以避免模块加载时的错误
        import System
        from System.IO import FileStream, FileMode, FileAccess, FileShare
        from System.Collections.Generic import List as CsList

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

        # 绑定到实例
        self.System = System
        self.FileStream = FileStream
        self.FileMode = FileMode
        self.FileAccess = FileAccess
        self.FileShare = FileShare
        self.CsList = CsList  # 重命名避免冲突

        self.LegacyBeatmapDecoder = LegacyBeatmapDecoder
        self.LineBufferedReader = LineBufferedReader
        self.FlatWorkingBeatmap = FlatWorkingBeatmap

        self.HitResult = HitResult
        self.ScoreInfo = ScoreInfo
        self.Mod = Mod

        # Catch 对象类型
        self.CatchObjects = {
            'Fruit': Fruit,
            'Droplet': Droplet,
            'TinyDroplet': TinyDroplet,
            'JuiceStream': JuiceStream
        }

        # 初始化规则集
        self.rulesets: Dict[int, Any] = {
            0: OsuRuleset(),
            1: TaikoRuleset(),
            2: CatchRuleset(),
            3: ManiaRuleset()
        }
        self.prepared_cache_size = max(0, int(prepared_cache_size))
        self._prepared_cache: OrderedDict[Tuple[Any, ...], Tuple[Any, ...]] = OrderedDict()

    def clear_prepared_cache(self) -> None:
        """Release decoded beatmaps and difficulty attributes kept for reuse."""
        self._prepared_cache.clear()

    def _get_prepared_cache(self, key: Tuple[Any, ...]) -> Optional[Tuple[Any, ...]]:
        prepared = self._prepared_cache.get(key)
        if prepared is not None:
            self._prepared_cache.move_to_end(key)
        return prepared

    def _put_prepared_cache(self, key: Tuple[Any, ...], prepared: Tuple[Any, ...]) -> None:
        if self.prepared_cache_size <= 0:
            return
        self._prepared_cache[key] = prepared
        self._prepared_cache.move_to_end(key)
        while len(self._prepared_cache) > self.prepared_cache_size:
            self._prepared_cache.popitem(last=False)

    def _parse_mods(self, mod_list: Union[List[str], List[Dict], List[Any]], ruleset: Any) -> Any:
        """
        将 Python 输入转换为 C# Mod 列表。
        :return: System.Collections.Generic.List<osu.Game.Rulesets.Mods.Mod>
        """
        available_mods = ruleset.CreateAllMods()
        csharp_mods = self.CsList[self.Mod]()

        if not mod_list:
            return csharp_mods

        for m in mod_list:
            target_acronym: Optional[str]

            if isinstance(m, str):
                target_acronym = m
            elif isinstance(m, dict):
                target_acronym = m.get("acronym") or m.get("Acronym")
            else:
                target_acronym = getattr(m, "acronym", None) or getattr(m, "Acronym", None)

            if not target_acronym:
                continue

            # 在 C# List 中查找
            found = next(
                (x for x in available_mods if str(x.Acronym).upper() == str(target_acronym).upper()),
                None
            )

            if found:
                csharp_mods.Add(found)

        return csharp_mods

    def _get_mod_acronym(self, mod: Union[str, Dict[str, Any], Any]) -> Optional[str]:
        if isinstance(mod, str):
            return mod
        if isinstance(mod, dict):
            return mod.get("acronym") or mod.get("Acronym")
        return getattr(mod, "acronym", None) or getattr(mod, "Acronym", None)

    def _filter_mods_for_converted_mania(
            self,
            mods: List[Union[str, Dict[str, Any], Any]]
    ) -> List[Union[str, Dict[str, Any], Any]]:
        key_mods = {"1K", "2K", "3K", "4K", "5K", "6K", "7K", "8K", "9K", "10K"}
        return [mod for mod in mods if (self._get_mod_acronym(mod) or "").upper() not in key_mods]

    def _mods_cache_key(self, mods: Optional[Sequence[Union[str, Dict[str, Any], Any]]]) -> Tuple[str, ...]:
        if not mods:
            return tuple()
        return tuple((self._get_mod_acronym(mod) or "").upper() for mod in mods)

    def _get_request_value(self, request: Union[CalculationRequest, Dict[str, Any], Any], name: str, default: Any) -> Any:
        if isinstance(request, dict):
            return request.get(name, default)
        return getattr(request, name, default)

    def _normalize_request(self, request: Union[CalculationRequest, Dict[str, Any], Any]) -> Dict[str, Any]:
        mods = self._get_request_value(request, "mods", None)
        return {
            "file_path": self._get_request_value(request, "file_path", None),
            "mode": int(self._get_request_value(request, "mode", 0)),
            "mods": list(mods) if mods else [],
            "acc": float(self._get_request_value(request, "acc", 100.0)),
            "combo": self._get_request_value(request, "combo", None),
            "misses": int(self._get_request_value(request, "misses", 0)),
            "legacy_total_score": self._get_request_value(request, "legacy_total_score", None),
            "statistics": self._get_request_value(request, "statistics", None),
        }

    def _load_working_beatmap(self, abs_path: str, ruleset: Any) -> Tuple[Any, Any, int]:
        fs = None
        reader = None
        try:
            fs = self.FileStream(abs_path, self.FileMode.Open, self.FileAccess.Read, self.FileShare.Read)
            reader = self.LineBufferedReader(fs)
            decoder = self.LegacyBeatmapDecoder()
            beatmap = decoder.Decode(reader)

            original_ruleset_id = beatmap.BeatmapInfo.Ruleset.OnlineID
            converter = ruleset.CreateBeatmapConverter(beatmap)
            if converter.CanConvert():
                beatmap = converter.Convert()

            return beatmap, self.FlatWorkingBeatmap(beatmap), original_ruleset_id
        finally:
            if reader:
                reader.Dispose()
            if fs:
                fs.Dispose()

    def _calculate_prepared(
            self,
            mode: int,
            ruleset: Any,
            beatmap: Any,
            working_beatmap: Any,
            csharp_mods: Any,
            diff_attr: Any,
            acc: float,
            combo: Optional[int],
            misses: int,
            legacy_total_score: Optional[int],
            statistics: Optional[Union[Dict[str, int], Any]]
    ) -> CalculationResult:
        stats: Dict[Any, int] = {}

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
            stats = self._sim_mania(acc, beatmap, effective_misses, statistics)

        score = self.ScoreInfo()
        score.Ruleset = ruleset.RulesetInfo
        score.BeatmapInfo = working_beatmap.BeatmapInfo
        score.Mods = csharp_mods.ToArray()
        score.LegacyTotalScore = int(legacy_total_score) if legacy_total_score is not None and int(
            legacy_total_score) > 0 else 0
        score.MaxCombo = int(combo) if combo is not None else diff_attr.MaxCombo
        score.Accuracy = float(acc) / 100.0

        for result, count in stats.items():
            if count > 0:
                score.Statistics[result] = count

        perf_calc = ruleset.CreatePerformanceCalculator()
        pp_attr = perf_calc.Calculate(score, diff_attr)

        _aim = getattr(pp_attr, 'Aim', 0.0)
        _speed = getattr(pp_attr, 'Speed', 0.0)
        _acc = getattr(pp_attr, 'Accuracy', 0.0)
        _fl = getattr(pp_attr, 'Flashlight', 0.0)

        stats_readable = {str(k): v for k, v in stats.items()}

        return CalculationResult(
            mode=mode,
            stars=diff_attr.StarRating,
            pp=pp_attr.Total,
            pp_aim=_aim,
            pp_speed=_speed,
            pp_acc=_acc,
            pp_flashlight=_fl,
            max_combo=diff_attr.MaxCombo,
            stats_used=stats_readable
        )

    def _extract_stat(self, stats_obj: Union[Dict, Any, None], attr_name: str, default: int = 0) -> int:
        """安全提取统计属性"""
        if stats_obj is None:
            return default
        if isinstance(stats_obj, dict):
            # 支持 key 为 "Miss" 或 "miss"
            return stats_obj.get(attr_name, stats_obj.get(attr_name.capitalize(), default))
        return getattr(stats_obj, attr_name, default)

    def _has_valid_stats(self, stats_obj: Union[Dict, Any, None]) -> bool:
        """检查是否有有效统计数据"""
        if not stats_obj:
            return False
        keys = ['great', 'ok', 'meh', 'good', 'perfect', 'miss', 'large_tick_hit']
        for k in keys:
            if self._extract_stat(stats_obj, k) > 0:
                return True
        return False

    # ================= 模拟逻辑 (保持原有逻辑，仅添加类型提示) =================

    def _sim_osu(self, acc: float, beatmap: Any, misses: int, stats_obj: Any) -> Dict[Any, int]:
        if self._has_valid_stats(stats_obj):
            return {
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),
                self.HitResult.Ok: self._extract_stat(stats_obj, 'ok'),
                self.HitResult.Meh: self._extract_stat(stats_obj, 'meh'),
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss'),
                self.HitResult.SliderTailHit: self._extract_stat(stats_obj, 'slider_tail_hit'),
                self.HitResult.LargeTickHit: self._extract_stat(stats_obj, 'large_tick_hit'),
                self.HitResult.SmallTickHit: self._extract_stat(stats_obj, 'small_tick_hit'),
                self.HitResult.SmallTickMiss: self._extract_stat(stats_obj, 'small_tick_miss')
            }

        # Fallback 模拟
        total = beatmap.HitObjects.Count
        relevant = total - misses
        accuracy = acc / 100.0
        n300, n100, n50 = 0, 0, 0

        if relevant <= 0: return {self.HitResult.Miss: misses}
        rel_acc = max(0.0, min(1.0, accuracy * total / relevant))

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

    def _sim_taiko(self, acc: float, beatmap: Any, misses: int, stats_obj: Any) -> Dict[Any, int]:
        if self._has_valid_stats(stats_obj):
            return {
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),
                self.HitResult.Ok: self._extract_stat(stats_obj, 'ok'),
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss')
            }

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

    def _sim_mania(self, acc: float, beatmap: Any, misses: int, stats_obj: Any) -> Dict[Any, int]:
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

    def _sim_catch(self, acc: float, beatmap: Any, misses: int, stats_obj: Any) -> Dict[Any, int]:
        if self._has_valid_stats(stats_obj):
            return {
                self.HitResult.Great: self._extract_stat(stats_obj, 'great'),
                self.HitResult.LargeTickHit: self._extract_stat(stats_obj, 'large_tick_hit'),
                self.HitResult.SmallTickHit: self._extract_stat(stats_obj, 'small_tick_hit'),
                self.HitResult.SmallTickMiss: self._extract_stat(stats_obj, 'small_tick_miss'),
                self.HitResult.Miss: self._extract_stat(stats_obj, 'miss')
            }

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
        count_droplets = max(0, max_droplets - misses)

        return {
            self.HitResult.Great: max_fruits,
            self.HitResult.LargeTickHit: count_droplets,
            self.HitResult.SmallTickHit: max_tiny_droplets,
            self.HitResult.Miss: misses
        }

    # ================= 主计算函数 =================

    def calculate(
            self,
            file_path: str,
            mode: int = 0,
            mods: Optional[List[Union[str, Dict[str, Any], Any]]] = None,
            acc: float = 100.0,
            combo: Optional[int] = None,
            misses: int = 0,
            legacy_total_score: Optional[int] = None,
            statistics: Optional[Union[Dict[str, int], Any]] = None
    ) -> CalculationResult:
        """
        Calculates Performance Points (PP) and Star Rating (SR).

        :param file_path: Path to the .osu beatmap file.
        :param mode: Game mode (0=Osu, 1=Taiko, 2=Catch, 3=Mania).
        :param mods: List of mods. Supports strings (e.g. ["HD"]) or dicts (e.g. [{"acronym": "HD"}]).
        :param acc: Accuracy (0-100). Ignored in Standard mode if 'statistics' is provided.
        :param combo: Max combo achieved. If None, defaults to FC (Full Combo).
        :param misses: Miss count. Ignored if 'statistics' contains miss count.
        :param legacy_total_score: Legacy Total Score. Set to > 0 to enable osu!stable compatibility mode (Legacy Mode).
        :param statistics: Detailed hit statistics (dict or object), e.g. {'great': 300, 'ok': 10}.
        :return: CalculationResult object.
        """
        request = CalculationRequest(
            file_path=file_path,
            mode=mode,
            mods=mods,
            acc=acc,
            combo=combo,
            misses=misses,
            legacy_total_score=legacy_total_score,
            statistics=statistics
        )
        return self.calculate_many([request])[0]

    def calculate_many(
            self,
            requests: Sequence[Union[CalculationRequest, Dict[str, Any], Any]]
    ) -> List[CalculationResult]:
        """
        Batch-calculate PP/SR.

        Requests with the same file_path, mode, and mods share beatmap decoding,
        ruleset conversion, mod parsing, and difficulty calculation. Different
        acc/combo/miss/statistics values still get their own performance result.
        """
        normalized_requests = [self._normalize_request(request) for request in requests]
        results: List[Optional[CalculationResult]] = [None] * len(normalized_requests)
        groups: Dict[Tuple[str, int, Tuple[str, ...]], List[int]] = {}

        for index, request in enumerate(normalized_requests):
            file_path = request["file_path"]
            if not file_path:
                results[index] = CalculationResult(error="Missing file_path")
                continue

            abs_path = os.path.abspath(file_path)
            request["abs_path"] = abs_path

            if not os.path.exists(abs_path):
                results[index] = CalculationResult(error=f"File not found: {abs_path}")
                continue

            mode = request["mode"]
            if mode not in self.rulesets:
                results[index] = CalculationResult(error=f"Invalid mode: {mode}")
                continue

            key = (abs_path, mode, self._mods_cache_key(request["mods"]))
            groups.setdefault(key, []).append(index)

        for (abs_path, mode, mods_key), indexes in groups.items():
            ruleset = self.rulesets[mode]
            try:
                first_request = normalized_requests[indexes[0]]
                mods = first_request["mods"]
                stat = os.stat(abs_path)
                cache_key = (abs_path, mode, mods_key, stat.st_mtime_ns, stat.st_size)
                prepared = self._get_prepared_cache(cache_key)
                if prepared is None:
                    beatmap, working_beatmap, original_ruleset_id = self._load_working_beatmap(abs_path, ruleset)

                    if mode == 3 and original_ruleset_id != 3:
                        mods = self._filter_mods_for_converted_mania(mods)

                    csharp_mods = self._parse_mods(mods, ruleset)
                    diff_calc = ruleset.CreateDifficultyCalculator(working_beatmap)
                    diff_attr = diff_calc.Calculate(csharp_mods)
                    prepared = (beatmap, working_beatmap, csharp_mods, diff_attr)
                    self._put_prepared_cache(cache_key, prepared)
                else:
                    beatmap, working_beatmap, csharp_mods, diff_attr = prepared

                for index in indexes:
                    request = normalized_requests[index]
                    results[index] = self._calculate_prepared(
                        mode=mode,
                        ruleset=ruleset,
                        beatmap=beatmap,
                        working_beatmap=working_beatmap,
                        csharp_mods=csharp_mods,
                        diff_attr=diff_attr,
                        acc=request["acc"],
                        combo=request["combo"],
                        misses=request["misses"],
                        legacy_total_score=request["legacy_total_score"],
                        statistics=request["statistics"]
                    )

            except Exception as e:
                import traceback
                traceback.print_exc()
                error = str(e)
                for index in indexes:
                    results[index] = CalculationResult(error=error)

        return [result if result is not None else CalculationResult(error="Unknown calculation error") for result in results]
