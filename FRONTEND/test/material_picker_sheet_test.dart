import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';
import 'package:k_dpp/services/material_catalog_controller.dart';
import 'package:k_dpp/widgets/material_picker_sheet.dart';

// 불러오는 중에는 진행 표시가 계속 돌아 pumpAndSettle이 끝나지 않으므로
// 시트 열기·닫기는 시간을 정해 진행한다.
void main() {
  test('검색 결과는 이름·별칭이 같은 것, 앞글자가 같은 것, 포함하는 것 순이다', () {
    List<String> namesFor(String query) => rankMaterialCatalog(
      _catalogItems,
      query,
    ).map((item) => item.nameKo).toList();

    // '모'는 울의 별칭과 같고, 모달·모헤어는 '모'로 시작하며, 다운은 별칭 '우모'에 포함한다.
    expect(namesFor('모'), ['울', '모달', '모헤어', '다운']);
    expect(namesFor('COT'), ['면']);
    expect(namesFor('ton'), ['면']);
    expect(namesFor('  '), _catalogItems.map((item) => item.nameKo).toList());
    expect(namesFor('없는소재'), isEmpty);
  });

  test('다른 줄 소재는 한글명·영문명·별칭 어느 것으로 적었든 목록에서 빠진다', () {
    List<String> namesAfter(List<String> excludedNames) =>
        excludeMaterialCatalog(
          _catalogItems,
          excludedNames,
        ).map((item) => item.nameKo).toList();

    // 코튼 = 면, WOOL = 울, 우모 = 다운(별칭). 대소문자·앞뒤 공백은 무시한다.
    expect(namesAfter(['코튼', ' WOOL ', '우모']), ['비스코스', '모달', '모헤어']);
    // 부분 일치가 아니라 표준명이 같아야 빠진다 — '모'는 울의 별칭이지 모달·모헤어가 아니다.
    expect(namesAfter(['모']), ['면', '비스코스', '모달', '다운', '모헤어']);
    // 빈 이름은 무시하고, 뺄 것이 없으면 목록을 그대로 돌려준다.
    expect(
      identical(excludeMaterialCatalog(_catalogItems, ['', '  ']), _catalogItems),
      isTrue,
    );
  });

  testWidgets('다른 줄 소재가 있으면 안내를 덧붙이고, 검색한 소재가 그중 하나면 이유를 말한다', (
    tester,
  ) async {
    _usePhoneView(tester);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    await _openPicker(tester, catalog, excludedNames: ['면']);

    expect(
      find.text('한글명·영문명·별칭으로 찾을 수 있어요.\n다른 줄에 이미 넣은 소재는 목록에 없어요.'),
      findsOneWidget,
    );
    expect(_resultNames(tester), ['비스코스', '울', '모달', '다운', '모헤어']);

    // '면'을 검색하면 목록엔 없지만 "검색어에 맞는 소재가 없다"는 말은 틀리다.
    await tester.enterText(find.byType(TextField), '면');
    await tester.pump();

    expect(find.byType(ListTile), findsNothing);
    expect(
      find.text('검색한 소재는 다른 줄에 이미 넣었어요.\n다른 소재를 찾거나 입력란에 직접 입력해 주세요.'),
      findsOneWidget,
    );
  });

  testWidgets('다른 줄에 모든 소재를 넣었으면 남은 소재가 없다고 안내한다', (tester) async {
    _usePhoneView(tester);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    await _openPicker(
      tester,
      catalog,
      excludedNames: _catalogItems.map((item) => item.nameEn).toList(),
    );

    expect(find.byType(ListTile), findsNothing);
    expect(
      find.text('남은 소재가 없어요.\n다른 줄에 이미 넣은 소재는 목록에서 빠져요.'),
      findsOneWidget,
    );
  });

  testWidgets('입력란 글자로 검색이 채워진 채 열리고, 고른 소재를 반환한다', (tester) async {
    _usePhoneView(tester);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    final picked = await _openPicker(tester, catalog, initialQuery: '코');

    expect(find.widgetWithText(TextField, '코'), findsOneWidget);
    expect(_resultNames(tester), ['면', '비스코스']);

    await tester.tap(find.text('면'));
    await _pumpSheetAnimation(tester);

    expect(picked.completed, isTrue);
    expect(picked.item?.nameKo, '면');
  });

  testWidgets('검색어를 지우면 전체 소재가 보인다', (tester) async {
    _usePhoneView(tester);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    await _openPicker(tester, catalog, initialQuery: '모');
    expect(_resultNames(tester), hasLength(4));

    await tester.tap(find.byTooltip('검색어 지우기'));
    await tester.pump();

    expect(_resultNames(tester), hasLength(_catalogItems.length));
  });

  testWidgets('한 번도 받지 않은 목록은 열 때 요청하고, 받는 동안 안내한 뒤 목록으로 바꾼다', (
    tester,
  ) async {
    _usePhoneView(tester);
    final response = Completer<List<MaterialCatalogItem>>();
    var fetchCount = 0;
    final catalog = MaterialCatalogController(
      fetchMaterials: () {
        fetchCount++;
        return response.future;
      },
    );
    addTearDown(catalog.dispose);

    await _openPicker(tester, catalog);

    expect(fetchCount, 1);
    expect(find.text('소재 목록을 불러오는 중이에요.'), findsOneWidget);

    response.complete(_catalogItems);
    await tester.pump();
    await tester.pump();

    expect(find.text('소재 목록을 불러오는 중이에요.'), findsNothing);
    expect(_resultNames(tester), hasLength(_catalogItems.length));
  });

  testWidgets('불러오기에 실패했으면 안내와 다시 불러오기 버튼을 보이고, 누르면 다시 요청한다', (
    tester,
  ) async {
    _usePhoneView(tester);
    var shouldFail = true;
    var fetchCount = 0;
    final catalog = MaterialCatalogController(
      fetchMaterials: () async {
        fetchCount++;
        if (shouldFail) throw Exception('network');
        return _catalogItems;
      },
    );
    addTearDown(catalog.dispose);

    // 첫 실패의 로그만 가린다. 테스트가 끝날 때 debugPrint가 바뀌어 있으면
    // 프레임워크가 실패로 처리하므로 곧바로 되돌린다.
    final originalDebugPrint = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {};
    await catalog.load();
    debugPrint = originalDebugPrint;

    await _openPicker(tester, catalog);

    // 실패한 목록은 열 때 저절로 다시 요청하지 않고 사용자에게 맡긴다.
    expect(fetchCount, 1);
    expect(
      find.text('소재 목록을 불러오지 못했어요.\n입력란에 직접 입력하거나 다시 불러와 주세요.'),
      findsOneWidget,
    );

    shouldFail = false;
    await tester.tap(find.text('다시 불러오기'));
    await tester.pump();
    await tester.pump();

    expect(fetchCount, 2);
    expect(_resultNames(tester), hasLength(_catalogItems.length));
  });

  testWidgets('검색어에 맞는 소재가 없으면 직접 입력을 안내한다', (tester) async {
    _usePhoneView(tester);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    await _openPicker(tester, catalog, initialQuery: '없는소재');

    expect(find.byType(ListTile), findsNothing);
    expect(
      find.text('검색어에 맞는 소재가 없어요.\n입력란에 직접 입력할 수도 있어요.'),
      findsOneWidget,
    );
  });

  testWidgets('목록 한 줄은 버튼으로 읽히고 누를 수 있는 높이가 48dp 이상이다', (tester) async {
    final semantics = tester.ensureSemantics();
    _usePhoneView(tester);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    await _openPicker(tester, catalog);

    expect(
      tester.getSemantics(find.text('면')),
      isSemantics(isButton: true, hasTapAction: true),
    );
    expect(
      tester.getSize(find.byType(ListTile).first).height,
      greaterThanOrEqualTo(48),
    );
    semantics.dispose();
  });
}

const _catalogItems = [
  MaterialCatalogItem(id: 1, nameKo: '면', nameEn: 'cotton', aliases: ['코튼']),
  MaterialCatalogItem(id: 2, nameKo: '비스코스', nameEn: 'viscose', aliases: []),
  MaterialCatalogItem(id: 3, nameKo: '울', nameEn: 'wool', aliases: ['모']),
  MaterialCatalogItem(id: 4, nameKo: '모달', nameEn: 'modal', aliases: []),
  MaterialCatalogItem(id: 5, nameKo: '다운', nameEn: 'down', aliases: ['우모']),
  MaterialCatalogItem(id: 6, nameKo: '모헤어', nameEn: 'mohair', aliases: []),
];

class _PickResult {
  bool completed = false;
  MaterialCatalogItem? item;
}

Future<MaterialCatalogController> _loadedCatalog() async {
  final catalog = MaterialCatalogController(
    fetchMaterials: () async => _catalogItems,
  );
  await catalog.load();
  return catalog;
}

void _usePhoneView(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.625;
  addTearDown(tester.view.reset);
}

Future<void> _pumpSheetAnimation(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

Future<_PickResult> _openPicker(
  WidgetTester tester,
  MaterialCatalogController catalog, {
  String initialQuery = '',
  List<String> excludedNames = const [],
}) async {
  final picked = _PickResult();

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: ElevatedButton(
              onPressed: () {
                showMaterialPickerSheet(
                  context: context,
                  catalog: catalog,
                  initialQuery: initialQuery,
                  excludedNames: excludedNames,
                ).then((item) {
                  picked
                    ..completed = true
                    ..item = item;
                });
              },
              child: const Text('선택창 열기'),
            ),
          ),
        ),
      ),
    ),
  );

  await tester.tap(find.text('선택창 열기'));
  await _pumpSheetAnimation(tester);
  return picked;
}

List<String> _resultNames(WidgetTester tester) {
  return tester
      .widgetList<ListTile>(find.byType(ListTile))
      .map((tile) => (tile.title! as Text).data!)
      .toList();
}
