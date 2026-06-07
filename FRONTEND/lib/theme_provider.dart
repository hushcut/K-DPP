import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ThemeProvider extends ChangeNotifier {
  static const String _themeModeKey = 'theme_mode';

  ThemeProvider({SharedPreferencesAsync? preferences})
    : _preferences = preferences;

  SharedPreferencesAsync? _preferences;

  SharedPreferencesAsync get _prefs =>
      _preferences ??= SharedPreferencesAsync();

  ThemeMode _themeMode = ThemeMode.system;

  ThemeMode get themeMode => _themeMode;

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
