import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';
import 'package:k_dpp/services/material_catalog_controller.dart';
import 'package:k_dpp/theme/app_theme.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';
import 'package:k_dpp/widgets/material_picker_sheet.dart';

// 2026-09-22 폰 확인: 의류 종류 시트를 연 채 시스템 다크 모드를 끄면 글자만 검게 바뀌고
// 배경은 검은 채 남았다. 시트를 여는 쪽이 배경색을 여는 순간에 정했기 때문이다.
// 배경은 테마(bottomSheetTheme)에서 읽어야 시트가 열린 채로도 따라온다.
void main() {
  const darkSheet = Color(0xFF121212);

  test('라이트·다크 테마에 시트 배경색이 정해져 있다', () {
    expect(AppTheme.light().bottomSheetTheme.modalBackgroundColor, Colors.white);
    expect(AppTheme.dark().bottomSheetTheme.modalBackgroundColor, darkSheet);
  });

  testWidgets('의류 종류 시트는 열린 채 시스템이 다크→라이트로 바뀌면 배경과 글자가 함께 바뀐다', (
    tester,
  ) async {
    _usePhoneView(tester);
    await _pumpSystemThemedApp(
      tester,
      openSheet: (context) => showClothingTypePickerSheet(
        context: context,
        options: ClothingTypeCatalog.options,
        initialSelection: ClothingTypeCatalog.defaultOption,
      ),
    );

    expect(_sheetBackground(tester), darkSheet);
    final darkTitle = _textColor(tester, '의류 종류 선택');

    tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
    await tester.pumpAndSettle();

    expect(_sheetBackground(tester), Colors.white);
    expect(_textColor(tester, '의류 종류 선택'), isNot(darkTitle));
  });

  testWidgets('소재 선택창도 열린 채 시스템이 다크→라이트로 바뀌면 배경이 바뀐다', (tester) async {
    _usePhoneView(tester);
    final catalog = MaterialCatalogController(
      fetchMaterials: () async => const [
        MaterialCatalogItem(id: 1, nameKo: '면', nameEn: 'cotton', aliases: []),
      ],
    );
    addTearDown(catalog.dispose);
    await catalog.load();

    await _pumpSystemThemedApp(
      tester,
      openSheet: (context) =>
          showMaterialPickerSheet(context: context, catalog: catalog),
    );
    expect(_sheetBackground(tester), darkSheet);

    tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
    await tester.pumpAndSettle();

    expect(_sheetBackground(tester), Colors.white);
  });
}

/// 앱과 같은 테마(AppTheme)를 시스템 밝기 따름으로 띄우고, 다크인 상태에서 시트를 연다.
Future<void> _pumpSystemThemedApp(
  WidgetTester tester, {
  required Future<void> Function(BuildContext context) openSheet,
}) async {
  tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);

  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.system,
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => openSheet(context),
            child: const Text('시트 열기'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('시트 열기'));
  await tester.pumpAndSettle();
}

Color? _sheetBackground(WidgetTester tester) {
  return tester
      .widget<Material>(
        find
            .descendant(
              of: find.byType(BottomSheet),
              matching: find.byType(Material),
            )
            .first,
      )
      .color;
}

Color _textColor(WidgetTester tester, String text) {
  return tester.widget<Text>(find.text(text).first).style!.color!;
}

void _usePhoneView(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
}
