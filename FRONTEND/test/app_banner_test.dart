import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/main.dart';
import 'package:k_dpp/material_name_display_provider.dart';
import 'package:k_dpp/theme/app_palette.dart';
import 'package:k_dpp/theme/app_theme.dart';
import 'package:k_dpp/theme_provider.dart';
import 'package:k_dpp/widgets/app_banner.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_closet_storage.dart';

// 알림 29곳을 대신하는 앱바 아래 공용 배너(DECISIONS 76·88)의 규칙을 고정한다.
void main() {
  group('표시 시간', () {
    test('짧은 문장은 종류 기본값 — 성공 2.5초, 실패·안내 4초', () {
      expect(
        AppBanner.durationFor('의류 정보가 수정됐어요.', AppBannerKind.success),
        const Duration(milliseconds: 2500),
      );
      expect(
        AppBanner.durationFor('저장하지 못했어요.', AppBannerKind.failure),
        const Duration(seconds: 4),
      );
      expect(
        AppBanner.durationFor('이미 옷장에서 삭제된 의류예요.', AppBannerKind.info),
        const Duration(seconds: 4),
      );
    });

    test('긴 문장은 1초 + 공백 뺀 글자당 0.1초가 하한이다', () {
      // 28자: 둘째 문장이 새 정보라 성공 기본값 2.5초로는 짧다.
      expect(
        AppBanner.durationFor(
          '비밀번호가 바뀌었어요. 다른 기기에서는 다시 로그인해야 해요.',
          AppBannerKind.success,
        ),
        const Duration(milliseconds: 3800),
      );
      // 43자: 가장 긴 앱 문구(스캔 중 로그인 만료 + 정리 실패).
      expect(
        AppBanner.durationFor(
          '로그인 정보가 만료되었어요. 다시 로그인한 뒤 스캔해 주세요. 일부 로그인 정보는 지우지 못했어요.',
          AppBannerKind.failure,
        ),
        const Duration(milliseconds: 5300),
      );
      // 공백·줄바꿈은 세지 않는다.
      expect(
        AppBanner.durationFor('${'가 ' * 40}\n', AppBannerKind.failure),
        const Duration(seconds: 5),
      );
    });

    test('읽기 프로그램이 켜지면 평소 시간(종류 기본값과 하한 중 큰 쪽)의 두 배', () {
      expect(
        AppBanner.durationFor(
          '의류 정보가 수정됐어요.',
          AppBannerKind.success,
          accessibleNavigation: true,
        ),
        const Duration(seconds: 5),
      );
      expect(
        AppBanner.durationFor(
          '저장하지 못했어요.',
          AppBannerKind.failure,
          accessibleNavigation: true,
        ),
        const Duration(seconds: 8),
      );
      expect(
        AppBanner.durationFor(
          '가' * 100,
          AppBannerKind.info,
          accessibleNavigation: true,
        ),
        const Duration(seconds: 22),
      );
    });
  });

  group('배너 호스트', () {
    testWidgets('앱바 아래 고정 위치(위 안전 영역 + 56 + 8)에 뜨고, 앱바 없는 화면에서도 같은 자리다', (
      tester,
    ) async {
      _useIPhoneView(tester);
      await _pumpApp(tester);

      _banner(tester).show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pumpAndSettle();

      final rect = tester.getRect(find.byType(AppBannerView));
      expect(rect.top, 62 + kToolbarHeight + 8);
      expect(rect.left, 16);
      expect(rect.right, 440 - 16);

      await _openNoAppBarPage(tester);

      expect(find.text('앱바 없는 화면'), findsOneWidget);
      expect(tester.getRect(find.byType(AppBannerView)).top, 126);
    });

    testWidgets('화면을 넘어가도 남는다', (tester) async {
      await _pumpApp(tester);

      _banner(tester).show(
        '로그인이 만료됐어요. 다시 로그인해 주세요.',
        kind: AppBannerKind.info,
      );
      await tester.pump();
      await _openNoAppBarPage(tester);

      expect(find.text('첫 화면'), findsNothing);
      expect(find.text('로그인이 만료됐어요. 다시 로그인해 주세요.'), findsOneWidget);
    });

    testWidgets('종류 기본 시간이 지나면 닫힌다', (tester) async {
      await _pumpApp(tester);
      final banner = _banner(tester);

      banner.show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 2400));
      expect(find.byType(AppBannerView), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsNothing);

      banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 3900));
      expect(find.byType(AppBannerView), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsNothing);
    });

    testWidgets('새 알림은 줄 세우지 않고 바로 바꾸며, 시간도 새로 센다', (tester) async {
      await _pumpApp(tester);
      final banner = _banner(tester);

      banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pump();
      await tester.pump(const Duration(seconds: 3));

      banner.show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pump();

      expect(find.text('저장하지 못했어요.'), findsNothing);
      expect(find.text('의류 정보가 수정됐어요.'), findsOneWidget);

      // 앞 알림의 4초가 지나도 새 알림은 자기 2.5초를 다 채운다.
      await tester.pump(const Duration(milliseconds: 2400));
      expect(find.text('의류 정보가 수정됐어요.'), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 200));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsNothing);
    });

    testWidgets('탭하면 닫힌다', (tester) async {
      await _pumpApp(tester);

      _banner(tester).show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pumpAndSettle();
      await tester.tap(find.byType(AppBannerView));
      await tester.pumpAndSettle();

      expect(find.byType(AppBannerView), findsNothing);
    });

    testWidgets('위로 밀면 닫히고, 아래로 밀면 그대로다', (tester) async {
      await _pumpApp(tester);

      _banner(tester).show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pumpAndSettle();

      await tester.drag(find.byType(AppBannerView), const Offset(0, 40));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsOneWidget);

      await tester.drag(find.byType(AppBannerView), const Offset(0, -40));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsNothing);
    });

    testWidgets('하단 시트가 열려 있어도 배너가 위에 보이고, 배너만 눌러 닫힌다', (tester) async {
      await _pumpApp(tester);

      showModalBottomSheet<void>(
        context: tester.element(find.text('첫 화면')),
        builder: (_) => const SizedBox(height: 200, child: Text('정렬 시트')),
      );
      await tester.pumpAndSettle();

      _banner(tester).show('정렬 방식을 저장하지 못해 이전 기준으로 되돌렸어요.', kind: AppBannerKind.failure);
      await tester.pumpAndSettle();

      await tester.tap(find.byType(AppBannerView));
      await tester.pumpAndSettle();

      expect(find.byType(AppBannerView), findsNothing);
      expect(find.text('정렬 시트'), findsOneWidget);
    });

    testWidgets('종류마다 아이콘이 다르다', (tester) async {
      await _pumpApp(tester);
      final banner = _banner(tester);

      for (final (kind, icon) in [
        (AppBannerKind.success, Icons.check_circle),
        (AppBannerKind.failure, Icons.error_outline),
        (AppBannerKind.info, Icons.info_outline),
      ]) {
        banner.show('알림 문구', kind: kind);
        await tester.pumpAndSettle();

        expect(
          find.descendant(
            of: find.byType(AppBannerView),
            matching: find.byIcon(icon),
          ),
          findsOneWidget,
          reason: '$kind',
        );
      }
    });

    testWidgets('카드는 앱 팔레트 색을 따른다(라이트·다크)', (tester) async {
      for (final (mode, palette) in [
        (ThemeMode.light, AppPalette.light),
        (ThemeMode.dark, AppPalette.dark),
      ]) {
        await _pumpApp(tester, themeMode: mode);

        _banner(tester).show('알림 문구', kind: AppBannerKind.info);
        await tester.pumpAndSettle();

        final card = tester.widget<Material>(
          find
              .descendant(
                of: find.byType(AppBannerView),
                matching: find.byType(Material),
              )
              .first,
        );
        expect(card.color, palette.card, reason: '$mode');

        final text = tester.widget<Text>(find.text('알림 문구'));
        expect(text.style?.color, palette.textPrimary, reason: '$mode');
      }
    });
  });

  group('읽기 프로그램', () {
    testWidgets('문구를 한 번만, 새로 나타난 live region 으로 읽고 탭·닫기 동작으로 닫힌다', (
      tester,
    ) async {
      final handle = tester.ensureSemantics();
      await _pumpApp(tester);
      final banner = _banner(tester);

      banner.show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pumpAndSettle();

      // 바깥 칸의 label 과 안쪽 Text 가 따로 있으면 두 번 읽힌다.
      expect(
        find.semantics.byPredicate(
          (node) => node.label.contains('의류 정보가 수정됐어요.'),
        ),
        findsOne,
      );
      final node = find.semantics.byLabel('의류 정보가 수정됐어요.').evaluate().single;
      expect(node.getSemanticsData().flagsCollection.isLiveRegion, isTrue);

      tester.semantics.dismiss(find.semantics.byLabel('의류 정보가 수정됐어요.'));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsNothing);

      banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pumpAndSettle();
      tester.semantics.tap(find.semantics.byLabel('저장하지 못했어요.'));
      await tester.pumpAndSettle();
      expect(find.byType(AppBannerView), findsNothing);

      handle.dispose();
    });

    testWidgets('같은 문구가 다시 와도 새 칸으로 바꿔 다시 읽게 한다', (tester) async {
      // iOS 는 live region 이 새로 생기거나 label 이 바뀔 때만 읽는다(SemanticsObject.mm 359-372).
      final handle = tester.ensureSemantics();
      await _pumpApp(tester);
      final banner = _banner(tester);

      banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pumpAndSettle();
      final firstId = find.semantics.byLabel('저장하지 못했어요.').evaluate().single.id;

      banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
      // 낭독 칸은 화면이 멈춘 프레임의 다음 프레임에 붙는다.
      await tester.pump();
      await tester.pump();
      final secondId = find.semantics.byLabel('저장하지 못했어요.').evaluate().single.id;

      expect(secondId, isNot(firstId));

      handle.dispose();
    });

    testWidgets('낭독 순서에서 배너는 화면 맨 앞이다(앱바 "<" 보다 먼저)', (tester) async {
      // 배너는 Navigator 와 형제라 화면 전체 칸과 위치로 정렬된다 — 가운데가 더 위라 앞에 온다.
      // 화면이 바뀔 때 VoiceOver 가 처음 짚는 자리도 이 배너가 된다.
      final handle = tester.ensureSemantics();
      _useIPhoneView(tester);
      await _pumpApp(tester);

      _banner(tester).show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pumpAndSettle();

      final labels = tester.semantics
          .simulatedAccessibilityTraversal()
          .map((node) => node.label.isEmpty ? node.tooltip : node.label)
          .where((label) => label.isNotEmpty)
          .toList();

      expect(labels.first, '저장하지 못했어요.');
      expect(labels.indexOf('첫 화면'), greaterThan(0));

      handle.dispose();
    });

    // 화면이 바뀔 때 Android·iOS 는 새 화면의 첫 칸에 초점을 준다. 그 순간 배너가 낭독 트리
    // 맨 앞에 있으면 live region 과 초점으로 두 번 읽힌다(DECISIONS 180).
    testWidgets('화면 전환과 같이 뜬 배너는 전환이 끝난 뒤에 낭독 칸이 생긴다', (tester) async {
      const message = '로그인이 만료됐어요. 다시 로그인해 주세요.';
      final handle = tester.ensureSemantics();
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await _pumpApp(tester);
      final navigator = Navigator.of(tester.element(find.text('첫 화면')));

      // 세션 만료처럼 배너를 띄우고 같은 순간 화면을 바꾼다.
      _banner(tester).show(message, kind: AppBannerKind.info);
      navigator.pushNamedAndRemoveUntil('/no-app-bar', (route) => false);

      int? routeFrame;
      int? oldRouteGoneFrame;
      int? liveFrame;
      var oldRouteGoneAtLive = false;
      for (var frame = 1; frame <= 120 && liveFrame == null; frame++) {
        await tester.pump(const Duration(milliseconds: 16));
        if (frame == 1) expect(find.text(message), findsOneWidget);

        if (routeFrame == null && _hasSemanticsLabel('앱바 없는 화면')) {
          routeFrame = frame;
        }
        if (oldRouteGoneFrame == null && !_hasSemanticsLabel('첫 화면')) {
          oldRouteGoneFrame = frame;
        }
        if (_isAnnounced(message)) {
          liveFrame = frame;
          oldRouteGoneAtLive = !_hasSemanticsLabel('첫 화면');
        }
      }

      expect(routeFrame, isNotNull);
      expect(liveFrame, greaterThan(routeFrame!));
      expect(oldRouteGoneAtLive, isTrue, reason: '전환이 끝나 앞 화면이 빠진 뒤');
      expect(oldRouteGoneFrame, isNotNull, reason: '전환이 끝난 프레임을 찾아야 틈을 잰다');
      expect(
        (liveFrame! - oldRouteGoneFrame!) * 16,
        greaterThanOrEqualTo(AppBanner.announceSettleDelay.inMilliseconds),
        reason: '새 화면의 첫 초점 낭독이 먼저 오게',
      );

      handle.dispose();
    });

    testWidgets('시트를 닫으며 뜬 배너는 시트가 다 내려가고 초점이 돌아갈 틈을 둔 뒤에 낭독 칸이 생긴다', (
      tester,
    ) async {
      const message = '의류 정보가 수정됐어요.';
      final handle = tester.ensureSemantics();
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await _pumpApp(tester);

      showModalBottomSheet<void>(
        context: tester.element(find.text('첫 화면')),
        builder: (_) => const SizedBox(height: 200, child: Text('수정 시트')),
      );
      await tester.pumpAndSettle();

      // 리포트 수정처럼 시트를 닫고 같은 순간 배너를 띄운다.
      Navigator.of(tester.element(find.text('수정 시트'))).pop();
      _banner(tester).show(message, kind: AppBannerKind.success);

      int? sheetGoneFrame;
      int? liveFrame;
      for (var frame = 1; frame <= 120 && liveFrame == null; frame++) {
        await tester.pump(const Duration(milliseconds: 16));
        if (sheetGoneFrame == null && !_hasSemanticsLabel('수정 시트')) {
          sheetGoneFrame = frame;
        }
        if (_isAnnounced(message)) liveFrame = frame;
      }

      expect(sheetGoneFrame, isNotNull);
      expect(liveFrame, isNotNull);
      // TalkBack 은 시트가 빠진 뒤 시트를 연 버튼으로 초점을 되돌리며 그 버튼을 읽는다(약 0.3초 뒤).
      // 그보다 먼저 낭독 칸이 생기면 배너를 읽다가 끊긴다(DECISIONS 194).
      expect(
        (liveFrame! - sheetGoneFrame!) * 16,
        greaterThanOrEqualTo(AppBanner.announceSettleDelay.inMilliseconds),
      );
      expect(
        (liveFrame - sheetGoneFrame) * 16,
        lessThan(AppBanner.announceSettleDelay.inMilliseconds + 100),
      );

      handle.dispose();
    });

    testWidgets('시트 뒤 배너 다음에 바로 띄운 배너는 틈 없이 낭독 칸이 생긴다', (tester) async {
      final handle = tester.ensureSemantics();
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await _pumpApp(tester);

      showModalBottomSheet<void>(
        context: tester.element(find.text('첫 화면')),
        builder: (_) => const SizedBox(height: 200, child: Text('수정 시트')),
      );
      await tester.pumpAndSettle();
      Navigator.of(tester.element(find.text('수정 시트'))).pop();
      _banner(tester).show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pumpAndSettle();
      await tester.pump(AppBanner.announceSettleDelay);
      expect(_isAnnounced('의류 정보가 수정됐어요.'), isTrue);

      // 아무것도 움직이지 않을 때 띄운 다음 배너는 앞 배너의 기다림을 물려받지 않는다.
      _banner(tester).show('저장하지 못했어요.', kind: AppBannerKind.failure);
      await tester.pump();
      await tester.pump();
      expect(_isAnnounced('저장하지 못했어요.'), isTrue);

      await tester.pump(const Duration(seconds: 10));
      handle.dispose();
    });

    testWidgets('끝나지 않는 애니메이션이 있어도 1초 안에 낭독 칸이 생긴다', (tester) async {
      const message = '저장하지 못했어요.';
      final handle = tester.ensureSemantics();
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await tester.pumpWidget(
        MaterialApp(
          builder: AppBannerHost.builder,
          home: Scaffold(
            appBar: AppBar(title: const Text('첫 화면')),
            body: const Center(child: CircularProgressIndicator()),
          ),
        ),
      );

      _banner(tester).show(message, kind: AppBannerKind.failure);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(_isAnnounced(message), isFalse, reason: '로딩 표시가 도는 동안은 기다린다');

      await tester.pump(
        AppBanner.announceWaitLimit - const Duration(milliseconds: 500),
      );
      await tester.pump();
      expect(_isAnnounced(message), isTrue);

      handle.dispose();
    });

    testWidgets('평소엔 위에서 미끄러져 내려온다', (tester) async {
      _useIPhoneView(tester);
      await _pumpApp(tester);

      _banner(tester).show('알림 문구', kind: AppBannerKind.info);
      await tester.pump();

      expect(tester.getRect(find.byType(AppBannerView)).top, lessThan(126));

      await tester.pumpAndSettle();
      expect(tester.getRect(find.byType(AppBannerView)).top, 126);
    });

    testWidgets('읽기 프로그램이 켜지면 슬라이드 없이 바로 뜨고 평소의 두 배(성공 5초) 동안 남는다', (
      tester,
    ) async {
      _useIPhoneView(tester);
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
      await _pumpApp(tester);

      _banner(tester).show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pump();
      expect(tester.getRect(find.byType(AppBannerView)).top, 126);

      await tester.pump(const Duration(milliseconds: 4900));
      expect(find.byType(AppBannerView), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byType(AppBannerView), findsNothing);
    });

    testWidgets('동작 줄이기는 슬라이드만 없애고 시간은 그대로다', (tester) async {
      _useIPhoneView(tester);
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
      await _pumpApp(tester);

      _banner(tester).show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
      await tester.pump();
      expect(tester.getRect(find.byType(AppBannerView)).top, 126);

      await tester.pump(const Duration(milliseconds: 2400));
      expect(find.byType(AppBannerView), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byType(AppBannerView), findsNothing);
    });
  });

  group('기록', () {
    // 기기에서 성공 배너가 일찍 닫힌 까닭을 logcat 으로 가린다(DECISIONS 180).
    testWidgets('표시와 닫힘을 이유·시간·읽기 프로그램 여부와 함께 남긴다', (tester) async {
      final handle = tester.ensureSemantics();
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await _pumpApp(tester);
      final banner = _banner(tester);

      final logs = <String>[];
      final originalDebugPrint = debugPrint;
      debugPrint = (message, {wrapWidth}) => logs.add(message ?? '');
      final originalLogEvents = AppBanner.logEvents;
      AppBanner.logEvents = true;

      try {
        banner.show('의류 정보가 수정됐어요.', kind: AppBannerKind.success);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 5100));

        banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
        await tester.pump();
        await tester.tap(find.byType(AppBannerView));
        await tester.pump();

        banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
        await tester.pump();
        await tester.drag(find.byType(AppBannerView), const Offset(0, -40));
        await tester.pump();

        banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
        await tester.pump();
        await tester.pump();
        tester.semantics.tap(find.semantics.byLabel('저장하지 못했어요.'));
        await tester.pump();

        banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
        await tester.pump();
        await tester.pump();
        tester.semantics.dismiss(find.semantics.byLabel('저장하지 못했어요.'));
        await tester.pump();

        banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
        await tester.pump();
        banner.show('알림 문구', kind: AppBannerKind.info);
        await tester.pump();
        banner.hide();
        await tester.pump();
      } finally {
        debugPrint = originalDebugPrint;
        AppBanner.logEvents = originalLogEvents;
      }

      expect(
        logs.first,
        '[AppBanner] 표시 #0 success 5000ms 읽기프로그램=true "의류 정보가 수정됐어요."',
      );

      final closes = logs
          .map(
            RegExp(
              r'^\[AppBanner\] (닫힘|바뀜) #(\d+) (?:이유=(\w+) )?표시 뒤 \d+ms',
            ).firstMatch,
          )
          .nonNulls
          .map((match) => '${match[1]} #${match[2]} ${match[3] ?? ''}'.trim())
          .toList();
      expect(closes, [
        '닫힘 #0 timer',
        '닫힘 #1 tap',
        '닫힘 #2 swipe',
        '닫힘 #3 accessibilityTap',
        '닫힘 #4 accessibilityDismiss',
        '바뀜 #5',
        '닫힘 #6 call',
      ]);
      expect(
        logs.where((line) => line.startsWith('[AppBanner] 닫힘')),
        everyElement(endsWith('읽기프로그램=true')),
      );

      handle.dispose();
    });

    testWidgets('닫히는 중에 다시 불려도 한 번만 기록한다', (tester) async {
      await _pumpApp(tester);
      final banner = _banner(tester);

      final logs = <String>[];
      final originalDebugPrint = debugPrint;
      final originalLogEvents = AppBanner.logEvents;
      debugPrint = (message, {wrapWidth}) => logs.add(message ?? '');
      AppBanner.logEvents = true;

      try {
        banner.show('저장하지 못했어요.', kind: AppBannerKind.failure);
        await tester.pumpAndSettle();
        banner.hide();
        await tester.pump(const Duration(milliseconds: 50));
        banner.hide();
        await tester.pumpAndSettle();
      } finally {
        debugPrint = originalDebugPrint;
        AppBanner.logEvents = originalLogEvents;
      }

      expect(find.byType(AppBannerView), findsNothing);
      expect(
        logs.where((line) => line.startsWith('[AppBanner] 닫힘')),
        hasLength(1),
      );
    });
  });

  group('배선', () {
    testWidgets('호스트가 없으면 알아보기 쉬운 오류를 낸다', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(home: Scaffold(body: Text('호스트 없음'))),
      );

      expect(
        () => AppBanner.of(tester.element(find.text('호스트 없음'))),
        throwsFlutterError,
      );
    });

    testWidgets('MyApp 은 Navigator 위에 배너 호스트를 단다', (tester) async {
      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider(
              create: (_) => ClosetProvider(storage: FakeClosetStorage()),
            ),
            ChangeNotifierProvider(create: (_) => ThemeProvider()),
            ChangeNotifierProvider(create: (_) => MaterialNameDisplayProvider()),
          ],
          child: const MyApp(),
        ),
      );
      await tester.pump();

      expect(
        find.ancestor(
          of: find.byType(Navigator).first,
          matching: find.byType(AppBannerHost),
        ),
        findsOneWidget,
      );

      // 스플래시의 최소 표시 타이머가 남지 않게 화면을 내리고 시간을 흘려보낸다.
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 2));
    });

    test('앱 코드에 스낵바 호출이 남지 않는다(알림은 AppBanner 로)', () {
      final offenders = <String>[];

      for (final file in Directory('lib').listSync(recursive: true)) {
        if (file is! File || !file.path.endsWith('.dart')) continue;

        final lines = file.readAsLinesSync();
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i].trimLeft();
          if (line.startsWith('//')) continue;
          if (line.contains('showSnackBar') || line.contains('ScaffoldMessenger')) {
            offenders.add('${file.path}:${i + 1}');
          }
        }
      }

      expect(offenders, isEmpty);
    });
  });
}

/// iPhone 16 Pro Max 와 같은 논리 크기(440×956)와 위·아래 안전 영역(62·34)을 씁니다.
void _useIPhoneView(WidgetTester tester) {
  tester.view.devicePixelRatio = 3;
  tester.view.physicalSize = const Size(1320, 2868);
  tester.view.padding = const FakeViewPadding(top: 186, bottom: 102);
  tester.view.viewPadding = const FakeViewPadding(top: 186, bottom: 102);
  addTearDown(tester.view.reset);
}

Future<void> _pumpApp(
  WidgetTester tester, {
  ThemeMode themeMode = ThemeMode.light,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: themeMode,
      builder: AppBannerHost.builder,
      routes: {
        '/': (context) => Scaffold(
          appBar: AppBar(title: const Text('첫 화면')),
          body: const SizedBox.expand(),
        ),
        '/no-app-bar': (context) =>
            const Scaffold(body: Center(child: Text('앱바 없는 화면'))),
      },
    ),
  );
}

/// 낭독 트리에 [label] 칸이 있는지입니다.
bool _hasSemanticsLabel(String label) {
  return find.semantics
      .byPredicate((node) => node.label == label)
      .evaluate()
      .isNotEmpty;
}

/// [message] 배너의 낭독 칸(live region)이 붙었는지입니다.
bool _isAnnounced(String message) {
  return find.semantics
      .byPredicate(
        (node) =>
            node.label == message &&
            node.getSemanticsData().flagsCollection.isLiveRegion,
      )
      .evaluate()
      .isNotEmpty;
}

AppBannerHostState _banner(WidgetTester tester) {
  return AppBanner.of(tester.element(find.text('첫 화면')));
}

/// 세션 만료처럼 스택을 비우고 앱바 없는 화면으로 갑니다.
Future<void> _openNoAppBarPage(WidgetTester tester) async {
  Navigator.of(
    tester.element(find.text('첫 화면')),
  ).pushNamedAndRemoveUntil('/no-app-bar', (route) => false);
  await tester.pumpAndSettle();
}
