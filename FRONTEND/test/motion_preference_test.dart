import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/motion_preference.dart';

// DECISIONS 268: '동작 줄이기'는 Android '애니메이션 삭제'(disableAnimations)와 iOS '동작 줄이기'
// (reduceMotion)를 함께 보고, 앱 코드는 이 판정을 reducesMotion 한 곳에서만 합니다.
void main() {
  Future<bool> reducesMotionWith(
    WidgetTester tester,
    FakeAccessibilityFeatures features,
  ) async {
    tester.platformDispatcher.accessibilityFeaturesTestValue = features;
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);

    late bool result;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            result = reducesMotion(context);
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    return result;
  }

  testWidgets('아무것도 켜지 않으면 동작을 줄이지 않는다', (tester) async {
    expect(
      await reducesMotionWith(tester, const FakeAccessibilityFeatures()),
      isFalse,
    );
  });

  testWidgets('Android 애니메이션 삭제(disableAnimations)면 동작을 줄인다', (tester) async {
    expect(
      await reducesMotionWith(
        tester,
        const FakeAccessibilityFeatures(disableAnimations: true),
      ),
      isTrue,
    );
  });

  testWidgets(
    'iOS 동작 줄이기(reduceMotion)면 MediaQuery 에 실리지 않아도 동작을 줄인다',
    (tester) async {
      expect(
        await reducesMotionWith(
          tester,
          const FakeAccessibilityFeatures(
            reduceMotion: true,
            supportsAnnounce: true,
          ),
        ),
        isTrue,
      );
      // 판정이 MediaQuery 와 따로 가는 까닭입니다. Flutter 가 실어 주면 이 줄이 깨집니다.
      expect(
        MediaQuery.disableAnimationsOf(tester.element(find.byType(SizedBox))),
        isFalse,
      );
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  test('앱 코드는 동작 줄이기를 reducesMotion 으로만 본다', () {
    final offenders = <String>[];
    // maybeDisableAnimationsOf(대문자 D)와 MediaQueryData.disableAnimations 도 잡습니다.
    final pattern = RegExp(
      r'[dD]isableAnimationsOf|\.disableAnimations\b|\.reduceMotion\b',
    );

    for (final file in Directory('lib').listSync(recursive: true)) {
      if (file is! File || !file.path.endsWith('.dart')) continue;
      if (file.path.endsWith('motion_preference.dart')) continue;

      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i].trimLeft();
        if (line.startsWith('//')) continue;
        if (pattern.hasMatch(line)) offenders.add('${file.path}:${i + 1}');
      }
    }

    expect(offenders, isEmpty);
  });
}
