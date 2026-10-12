import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/navigation_bar_opacity_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

/// 하단 메뉴 배경 불투명도는 기기 단위 설정이다.
///
/// 앱을 다시 열어도 고른 값으로 시작해야 하고, 저장에 실패하면 화면이
/// 저장소와 어긋나지 않도록 마지막 저장값으로 돌아가야 한다.
void main() {
  setUp(() {
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
  });

  test('저장된 값이 없으면 85%로 시작한다', () async {
    final provider = NavigationBarOpacityProvider();

    await provider.load();

    expect(provider.opacity, 0.85);
  });

  test('고른 값은 앱을 다시 열어도 유지된다', () async {
    await NavigationBarOpacityProvider().setOpacity(0.7);

    // 새 Provider는 앱을 다시 연 상황이다. 메모리가 아니라 저장소에서 읽어야 한다.
    final reopened = NavigationBarOpacityProvider();
    await reopened.load();

    expect(reopened.opacity, 0.7);
    expect(
      await SharedPreferencesAsync().getDouble('navigation_bar_opacity'),
      0.7,
    );
  });

  test('범위 밖 저장값은 50~100% 안으로 되돌려 시작한다', () async {
    final prefs = SharedPreferencesAsync();

    await prefs.setDouble('navigation_bar_opacity', 0.2);
    final tooLow = NavigationBarOpacityProvider();
    await tooLow.load();
    expect(tooLow.opacity, 0.5);

    await prefs.setDouble('navigation_bar_opacity', 1.4);
    final tooHigh = NavigationBarOpacityProvider();
    await tooHigh.load();
    expect(tooHigh.opacity, 1.0);

    await prefs.setDouble('navigation_bar_opacity', double.nan);
    final invalid = NavigationBarOpacityProvider();
    await invalid.load();
    expect(invalid.opacity, 0.85);
  });

  test('setOpacity도 범위 밖 값을 잘라 저장한다', () async {
    final provider = NavigationBarOpacityProvider();

    await provider.setOpacity(0.1);

    expect(provider.opacity, 0.5);
    expect(
      await SharedPreferencesAsync().getDouble('navigation_bar_opacity'),
      0.5,
    );
  });

  test('preview는 화면에만 반영하고 저장하지 않는다', () async {
    final provider = NavigationBarOpacityProvider();
    var notified = 0;
    provider.addListener(() => notified++);

    provider.preview(0.65);

    expect(provider.opacity, 0.65);
    expect(notified, 1);
    expect(
      await SharedPreferencesAsync().getDouble('navigation_bar_opacity'),
      isNull,
    );

    // 같은 값이면 다시 알리지 않는다(슬라이더가 같은 칸 안에서 움직일 때).
    provider.preview(0.65);
    expect(notified, 1);
  });

  test('저장에 실패하면 마지막 저장값으로 되돌리고 예외를 다시 던진다', () async {
    final preferences = _ControlledPreferences();
    final provider = NavigationBarOpacityProvider(preferences: preferences);

    // 미리보기로 바꿔 둔 값이 아니라 저장소 값(기본 85%)으로 돌아가야 한다.
    provider.preview(0.65);
    final saving = provider.setOpacity(0.55);

    // 저장을 기다리지 않고 화면에 먼저 반영한다.
    expect(provider.opacity, 0.55);

    preferences.pending.single.completeError(StateError('저장소 오류'));
    await expectLater(saving, throwsStateError);

    expect(provider.opacity, 0.85);
  });

  test('먼저 보낸 저장이 늦게 실패해도 나중에 고른 값을 덮어쓰지 않는다', () async {
    final preferences = _ControlledPreferences();
    final provider = NavigationBarOpacityProvider(preferences: preferences);

    final firstSave = provider.setOpacity(0.7);
    final secondSave = provider.setOpacity(0.9);

    preferences.pending[1].complete();
    await secondSave;

    preferences.pending[0].completeError(StateError('저장소 오류'));
    await expectLater(firstSave, throwsStateError);

    expect(provider.opacity, 0.9);
  });

  test('먼저 보낸 저장이 늦게 성공해도 롤백 기준은 나중 값이다', () async {
    final preferences = _ControlledPreferences();
    final provider = NavigationBarOpacityProvider(preferences: preferences);

    final firstSave = provider.setOpacity(0.7);
    final secondSave = provider.setOpacity(0.9);
    preferences.pending[1].complete();
    await secondSave;
    preferences.pending[0].complete();
    await firstSave;

    // 세 번째 저장이 실패하면 0.7이 아니라 0.9로 돌아가야 한다.
    final thirdSave = provider.setOpacity(0.6);
    preferences.pending[2].completeError(StateError('저장소 오류'));
    await expectLater(thirdSave, throwsStateError);

    expect(provider.opacity, 0.9);
  });
}

/// 저장 호출마다 완료 시점을 테스트가 정할 수 있는 저장소입니다.
class _ControlledPreferences extends Fake implements SharedPreferencesAsync {
  final List<Completer<void>> pending = [];

  @override
  Future<void> setDouble(String key, double value) {
    final completer = Completer<void>();
    pending.add(completer);
    return completer.future;
  }
}
