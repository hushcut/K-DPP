// 사용자가 선택한 화면 테마를 메모리와 로컬 설정에 동기화하는 파일입니다.
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 라이트·다크·시스템 테마 상태를 보관하고 변경을 UI에 알립니다.
class ThemeProvider extends ChangeNotifier {
  static const String _themeModeKey = 'theme_mode';

  ThemeProvider({SharedPreferencesAsync? preferences})
    : _preferences = preferences;

  SharedPreferencesAsync? _preferences;

  SharedPreferencesAsync get _prefs =>
      _preferences ??= SharedPreferencesAsync();

  ThemeMode _themeMode = ThemeMode.system;

  // 저장 실패 롤백이 더 나중의 선택을 덮어쓰지 않도록 변경마다 올립니다.
  int _mutationVersion = 0;

  ThemeMode get themeMode => _themeMode;

  /// 기기에 저장된 문자열 값을 [ThemeMode]로 복원합니다.
  Future<void> loadThemeMode() async {
    final saved = await _prefs.getString(_themeModeKey);

    switch (saved) {
      case 'light':
        _themeMode = ThemeMode.light;
        break;
      case 'dark':
        _themeMode = ThemeMode.dark;
        break;
      default:
        _themeMode = ThemeMode.system;
    }

    notifyListeners();
  }

  /// 새 테마를 즉시 적용한 뒤 다음 실행을 위해 로컬 저장소에 기록합니다.
  /// 기록에 실패하면 다음 실행과 어긋나지 않도록 이전 테마로 되돌립니다.
  Future<void> setThemeMode(ThemeMode mode) async {
    final mutationVersion = ++_mutationVersion;
    final previousMode = _themeMode;
    _themeMode = mode;
    notifyListeners();

    final value = switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
    };

    try {
      await _prefs.setString(_themeModeKey, value);
    } catch (_) {
      // 이 호출 이후 더 새로운 선택이 반영됐다면 되돌리지 않습니다.
      if (mutationVersion == _mutationVersion) {
        _themeMode = previousMode;
        notifyListeners();
      }
      rethrow;
    }
  }
}
