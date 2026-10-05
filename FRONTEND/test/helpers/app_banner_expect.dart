import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/app_banner.dart';

/// 공용 배너가 그 문구·종류로 하나만 떠 있고 스낵바는 없는지 확인합니다.
///
/// 테스트 앱의 MaterialApp 에는 `builder: AppBannerHost.builder` 가 있어야 합니다.
void expectAppBanner(
  WidgetTester tester,
  String message,
  AppBannerKind kind,
) {
  expect(find.byType(SnackBar), findsNothing);

  final banner = find.byType(AppBannerView);
  expect(banner, findsOneWidget);

  final view = tester.widget<AppBannerView>(banner);
  expect(view.message, message);
  expect(view.kind, kind);
}
