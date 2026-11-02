import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/models/material_name_display.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

/// 소재 이름 표시 언어는 기기 단위 설정이다.
///
/// 앱을 다시 열어도 고른 언어로 시작해야 하고, 저장에 실패하면 화면이
/// 저장소와 어긋나지 않도록 이전 언어로 돌아가야 한다.
void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  test('저장된 값이 없으면 한글로 시작한다', () async {
    final provider = MaterialNameDisplayProvider();

    await provider.load();

    expect(provider.display, MaterialNameDisplay.korean);
  });

  test('고른 언어는 앱을 다시 열어도 유지된다', () async {
    for (final display in MaterialNameDisplay.values) {
      await MaterialNameDisplayProvider().setDisplay(display);

      // 새 Provider는 앱을 다시 연 상황이다. 메모리가 아니라 저장소에서 읽어야 한다.
      final reopened = MaterialNameDisplayProvider();
      await reopened.load();

      expect(reopened.display, display, reason: display.name);
    }
  });

  test('저장소에는 enum 이름이 아니라 storageValue를 기록한다', () async {
    await MaterialNameDisplayProvider().setDisplay(
      MaterialNameDisplay.koreanAndEnglish,
    );

    expect(
      await SharedPreferencesAsync().getString('material_name_display'),
      'ko_en',
    );
  });

  test('알 수 없는 저장값이면 한글로 시작한다', () async {
    await SharedPreferencesAsync().setString('material_name_display', 'fr');
    final provider = MaterialNameDisplayProvider();

    await provider.load();

    expect(provider.display, MaterialNameDisplay.korean);
  });

  test('저장에 실패하면 이전 언어로 되돌리고 예외를 다시 던진다', () async {
    final preferences = _ControlledPreferences();
    final provider = MaterialNameDisplayProvider(preferences: preferences);

    final saving = provider.setDisplay(MaterialNameDisplay.english);

    // 저장을 기다리지 않고 화면에 먼저 반영한다.
    expect(provider.display, MaterialNameDisplay.english);

    preferences.pending.single.completeError(StateError('저장소 오류'));
    await expectLater(saving, throwsStateError);

    expect(provider.display, MaterialNameDisplay.korean);
  });

  test('먼저 보낸 저장이 늦게 실패해도 나중에 고른 언어를 덮어쓰지 않는다', () async {
    final preferences = _ControlledPreferences();
    final provider = MaterialNameDisplayProvider(preferences: preferences);

    final firstSave = provider.setDisplay(MaterialNameDisplay.english);
    final secondSave = provider.setDisplay(
      MaterialNameDisplay.koreanAndEnglish,
    );

    preferences.pending[1].complete();
    await secondSave;

    preferences.pending[0].completeError(StateError('저장소 오류'));
    await expectLater(firstSave, throwsStateError);

    expect(provider.display, MaterialNameDisplay.koreanAndEnglish);
  });
}

/// 저장 호출마다 완료 시점을 테스트가 정할 수 있는 저장소입니다.
class _ControlledPreferences extends Fake implements SharedPreferencesAsync {
  final List<Completer<void>> pending = [];

  @override
  Future<void> setString(String key, String value) {
    final completer = Completer<void>();
    pending.add(completer);
    return completer.future;
  }
}
