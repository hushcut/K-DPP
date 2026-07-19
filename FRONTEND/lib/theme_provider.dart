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
  Future<void> setThemeMode(ThemeMode mode) async {
    _themeMode = mode;
    notifyListeners();

    final value = switch (mode) {
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
      ThemeMode.system => 'system',
    };

    await _prefs.setString(_themeModeKey, value);
  }
}
