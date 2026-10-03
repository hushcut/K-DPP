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
        AppBanner.durationFor('의류 정보가 수정되었습니다.', AppBannerKind.success),
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
      // 31자: 둘째 문장이 새 정보라 성공 기본값 2.5초로는 짧다.
      expect(
        AppBanner.durationFor(
          '비밀번호가 변경되었습니다. 다른 기기에서는 다시 로그인해야 합니다.',
          AppBannerKind.success,
        ),
        const Duration(milliseconds: 4100),
      );
      // 46자: 가장 긴 앱 문구(세션 만료 + 정리 실패).
      expect(
        AppBanner.durationFor(
          '로그인 세션이 만료되었습니다. 다시 로그인해 주세요. (저장된 로그인 정보 정리는 완료하지 못했습니다)',
          AppBannerKind.failure,
        ),
        const Duration(milliseconds: 5600),
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
          '의류 정보가 수정되었습니다.',
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

      _banner(tester).show('의류 정보가 수정되었습니다.', kind: AppBannerKind.success);
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
        '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.',
        kind: AppBannerKind.info,
      );
      await tester.pump();
      await _openNoAppBarPage(tester);

      expect(find.text('첫 화면'), findsNothing);
      expect(find.text('로그인 세션이 만료되었습니다. 다시 로그인해 주세요.'), findsOneWidget);
    });

    testWidgets('종류 기본 시간이 지나면 닫힌다', (tester) async {
      await _pumpApp(tester);
      final banner = _banner(tester);

      banner.show('의류 정보가 수정되었습니다.', kind: AppBannerKind.success);
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

      banner.show('의류 정보가 수정되었습니다.', kind: AppBannerKind.success);
      await tester.pump();

      expect(find.text('저장하지 못했어요.'), findsNothing);
      expect(find.text('의류 정보가 수정되었습니다.'), findsOneWidget);

      // 앞 알림의 4초가 지나도 새 알림은 자기 2.5초를 다 채운다.
      await tester.pump(const Duration(milliseconds: 2400));
      expect(find.text('의류 정보가 수정되었습니다.'), findsOneWidget);

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

      banner.show('의류 정보가 수정되었습니다.', kind: AppBannerKind.success);
      await tester.pumpAndSettle();

      // 바깥 칸의 label 과 안쪽 Text 가 따로 있으면 두 번 읽힌다.
      expect(
        find.semantics.byPredicate(
          (node) => node.label.contains('의류 정보가 수정되었습니다.'),
        ),
        findsOne,
      );
      final node = find.semantics.byLabel('의류 정보가 수정되었습니다.').evaluate().single;
      expect(node.getSemanticsData().flagsCollection.isLiveRegion, isTrue);

      tester.semantics.dismiss(find.semantics.byLabel('의류 정보가 수정되었습니다.'));
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

      _banner(tester).show('의류 정보가 수정되었습니다.', kind: AppBannerKind.success);
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

      _banner(tester).show('의류 정보가 수정되었습니다.', kind: AppBannerKind.success);
      await tester.pump();
      expect(tester.getRect(find.byType(AppBannerView)).top, 126);

      await tester.pump(const Duration(milliseconds: 2400));
      expect(find.byType(AppBannerView), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump();
      expect(find.byType(AppBannerView), findsNothing);
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
