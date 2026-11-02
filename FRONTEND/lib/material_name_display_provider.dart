// 사용자가 선택한 소재 이름 표시 언어를 메모리와 로컬 설정에 동기화하는 파일입니다.
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'models/material_name_display.dart';

/// 소재 이름 표시 언어(한글·영문·한글+영문) 상태를 보관하고 변경을 UI에 알립니다.
///
/// 기기 단위 설정입니다. 계정별 키를 쓰지 않아 로그아웃·계정 전환 뒤에도 유지됩니다.
class MaterialNameDisplayProvider extends ChangeNotifier {
  static const String _displayKey = 'material_name_display';

  MaterialNameDisplayProvider({SharedPreferencesAsync? preferences})
    : _preferences = preferences;

  SharedPreferencesAsync? _preferences;

  SharedPreferencesAsync get _prefs =>
      _preferences ??= SharedPreferencesAsync();

  MaterialNameDisplay _display = MaterialNameDisplay.korean;

  // 저장 실패 롤백이 더 나중의 선택을 덮어쓰지 않도록 변경마다 올립니다.
  int _mutationVersion = 0;

  MaterialNameDisplay get display => _display;

  /// 기기에 저장된 값을 복원합니다. 값이 없거나 알 수 없으면 한글입니다.
  Future<void> load() async {
    final saved = await _prefs.getString(_displayKey);
    _display = MaterialNameDisplay.fromStorage(saved);
    notifyListeners();
  }

  /// 새 표시 언어를 즉시 적용한 뒤 다음 실행을 위해 로컬 저장소에 기록합니다.
  /// 기록에 실패하면 다음 실행과 어긋나지 않도록 이전 값으로 되돌립니다.
  Future<void> setDisplay(MaterialNameDisplay display) async {
    final mutationVersion = ++_mutationVersion;
    final previousDisplay = _display;
    _display = display;
    notifyListeners();

    try {
      await _prefs.setString(_displayKey, display.storageValue);
    } catch (_) {
      // 이 호출 이후 더 새로운 선택이 반영됐다면 되돌리지 않습니다.
      if (mutationVersion == _mutationVersion) {
        _display = previousDisplay;
        notifyListeners();
      }
      rethrow;
    }
  }
}
