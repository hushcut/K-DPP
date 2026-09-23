// 사용자가 고른 하단 메뉴 배경 불투명도를 메모리와 로컬 설정에 동기화하는 파일입니다.
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 하단 내비게이션 바 배경의 불투명도(50~100%)를 보관하고 변경을 UI에 알립니다.
///
/// 기기 단위 설정입니다. 계정별 키를 쓰지 않아 로그아웃·계정 전환 뒤에도 유지됩니다.
class NavigationBarOpacityProvider extends ChangeNotifier {
  static const String _opacityKey = 'navigation_bar_opacity';

  /// 50% 아래는 뒤 글자가 비쳐 탭 이름을 읽기 어려워 여기서 막습니다(처음 60%였다가 사용자 요청으로 50%, 2026-09-23).
  static const double minOpacity = 0.5;
  static const double maxOpacity = 1.0;
  static const double defaultOpacity = 0.85;

  /// 슬라이더 한 칸입니다(5%).
  static const double step = 0.05;

  NavigationBarOpacityProvider({SharedPreferencesAsync? preferences})
    : _preferences = preferences;

  SharedPreferencesAsync? _preferences;

  SharedPreferencesAsync get _prefs =>
      _preferences ??= SharedPreferencesAsync();

  double _opacity = defaultOpacity;

  // 저장소에 실제로 기록된 값입니다. 저장에 실패하면 여기로 되돌립니다.
  double _savedOpacity = defaultOpacity;

  // 저장 실패 롤백이 더 나중의 선택을 덮어쓰지 않도록 변경마다 올립니다.
  int _mutationVersion = 0;
  int _savedVersion = 0;

  double get opacity => _opacity;

  /// 범위 밖 값과 NaN을 허용 범위 안으로 되돌립니다.
  static double clampOpacity(double value) {
    if (value.isNaN) return defaultOpacity;
    return value.clamp(minOpacity, maxOpacity).toDouble();
  }

  /// 기기에 저장된 값을 복원합니다. 값이 없으면 기본값(85%)입니다.
  Future<void> load() async {
    final saved = await _prefs.getDouble(_opacityKey);
    _opacity = saved == null ? defaultOpacity : clampOpacity(saved);
    _savedOpacity = _opacity;
    notifyListeners();
  }

  /// 슬라이더를 끄는 동안 저장 없이 화면에만 반영합니다. 손을 떼면 [setOpacity]로 저장합니다.
  void preview(double value) {
    final next = clampOpacity(value);
    if (next == _opacity) return;

    _opacity = next;
    notifyListeners();
  }

  /// 새 불투명도를 즉시 적용한 뒤 다음 실행을 위해 로컬 저장소에 기록합니다.
  /// 기록에 실패하면 다음 실행과 어긋나지 않도록 마지막으로 저장된 값으로 되돌립니다.
  Future<void> setOpacity(double value) async {
    final mutationVersion = ++_mutationVersion;
    final next = clampOpacity(value);
    _opacity = next;
    notifyListeners();

    try {
      await _prefs.setDouble(_opacityKey, next);
    } catch (_) {
      // 이 호출 이후 더 새로운 선택이 반영됐다면 되돌리지 않습니다.
      if (mutationVersion == _mutationVersion) {
        _opacity = _savedOpacity;
        notifyListeners();
      }
      rethrow;
    }

    // 먼저 보낸 저장이 늦게 끝나도 더 새로운 저장값을 덮어쓰지 않습니다.
    if (mutationVersion > _savedVersion) {
      _savedVersion = mutationVersion;
      _savedOpacity = next;
    }
  }
}
