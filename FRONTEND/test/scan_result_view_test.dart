import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';
import 'package:k_dpp/services/material_catalog_controller.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/utils/scan_form_validator.dart';
import 'package:k_dpp/widgets/material_input_collection.dart';
import 'package:k_dpp/widgets/scan_result_view.dart';

void main() {
  testWidgets('소재 합계가 100%가 아니면 부족한 비율을 안내한다', (tester) async {
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'cotton': 70, 'polyester': 20});
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: false,
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '찬물 세탁',
            originalMaterials: const {'cotton': 70, 'polyester': 20},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('현재 소재 합계: 90.0%'), findsOneWidget);
    expect(find.textContaining('100%까지 10% 부족해요.'), findsOneWidget);
  });

  testWidgets('스캔 실패 화면은 직접 소재 입력 흐름으로 분리된다', (tester) async {
    final materialInputs = MaterialInputCollection()..addEmpty();
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: true,
            scanFailureMessage: 'AI가 라벨을 정확히 인식하지 못했어요.',
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '라벨의 세탁 지침을 확인해 주세요.',
            originalMaterials: const {},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('스캔 실패'), findsOneWidget);
    expect(find.text('스캔 완료!'), findsNothing);
    expect(find.text('직접 소재 입력'), findsOneWidget);
    expect(find.text('직접 입력 모드'), findsOneWidget);
    expect(find.textContaining('AI가 라벨을 정확히 인식하지 못했어요.'), findsWidgets);
  });
  testWidgets('소재 입력 중에는 화면 전체를 다시 그리지 않고 합계만 갱신한다', (tester) async {
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'cotton': 70});
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: false,
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '찬물 세탁',
            originalMaterials: const {'cotton': 70},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('현재 소재 합계: 70.0%'), findsOneWidget);

    // 격리는 ScanResultView.build 안의 ListenableBuilder 두 구역으로 되어 있습니다.
    // 그 바깥 노드를 붙잡아 두고, 입력 뒤에도 같은 인스턴스인지 봅니다.
    // 상위 build가 다시 돌면 const가 아닌 Text가 새 인스턴스로 만들어져 깨집니다.
    //
    // 이전에는 ScanResultView **위**에 Builder를 두고 그 빌드 횟수를 셌는데,
    // 하위 리빌드는 상위 Element를 dirty로 만들지 않으므로 그 값은 격리가
    // 완전히 깨져도 늘지 않습니다. 즉 구조상 절대 실패할 수 없는 단언이었습니다.
    final headerBefore = tester.widget<Text>(find.text('스캔 완료!'));
    final sectionBefore = tester.widget<Text>(find.text('소재 및 혼용률'));

    await tester.enterText(find.text('70'), '100');
    await tester.pumpAndSettle();

    expect(find.text('현재 소재 합계: 100.0%'), findsOneWidget);
    expect(
      identical(tester.widget<Text>(find.text('스캔 완료!')), headerBefore),
      isTrue,
      reason: '소재 입력이 ListenableBuilder 구역 밖 헤더까지 다시 그리면 안 됩니다.',
    );
    expect(
      identical(tester.widget<Text>(find.text('소재 및 혼용률')), sectionBefore),
      isTrue,
      reason: '소재 입력이 섹션 제목까지 다시 그리면 격리가 깨진 것입니다.',
    );
  });
  testWidgets('소재명을 바꾸면 삭제 버튼 안내 문구도 즉시 따라간다', (tester) async {
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'cotton': 100});
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: false,
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '찬물 세탁',
            originalMaterials: const {'cotton': 100},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byTooltip('cotton 삭제'), findsOneWidget);

    // 낭독기 사용자가 옛 소재명을 듣지 않도록, 이름 수정이 즉시 반영돼야 합니다.
    await tester.enterText(find.text('cotton'), 'wool');
    await tester.pump();

    expect(find.byTooltip('wool 삭제'), findsOneWidget);
    expect(find.byTooltip('cotton 삭제'), findsNothing);
  });

  testWidgets('직접 입력 모드에서 인식된 라벨 원문을 보여 준다', (tester) async {
    final materialInputs = MaterialInputCollection()..addEmpty();
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: true,
            scanFailureMessage: 'AI가 라벨을 정확히 인식하지 못했어요.',
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '라벨의 세탁 지침을 확인해 주세요.',
            rawOcrPreview: 'COTTON 60% WOOL 15%',
            originalMaterials: const {},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    // 사진을 다시 열지 않고도 AI가 무엇을 읽었는지 확인할 수 있어야 합니다.
    expect(find.text('인식된 라벨 원문'), findsOneWidget);
    expect(find.text('COTTON 60% WOOL 15%'), findsOneWidget);
  });

  testWidgets('라벨 원문이 없으면 빈 안내 카드를 만들지 않는다', (tester) async {
    final materialInputs = MaterialInputCollection()..addEmpty();
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: true,
            scanFailureMessage: 'AI가 라벨을 정확히 인식하지 못했어요.',
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '라벨의 세탁 지침을 확인해 주세요.',
            rawOcrPreview: '   ',
            originalMaterials: const {},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('인식된 라벨 원문'), findsNothing);
  });

  testWidgets('자동 인식에 성공한 화면에는 라벨 원문을 끼워 넣지 않는다', (tester) async {
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'cotton': 100});
    final titleController = TextEditingController(text: '새로 스캔한 의류');
    addTearDown(materialInputs.dispose);
    addTearDown(titleController.dispose);

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ScanResultView(
            formKey: GlobalKey<FormState>(),
            hasTriedSubmit: false,
            isSaving: false,
            isScanFailed: false,
            titleController: titleController,
            selectedClothingType: ClothingTypeCatalog.defaultOption,
            materialInputs: materialInputs,
            scannedCare: '찬물 세탁',
            rawOcrPreview: 'COTTON 100%',
            originalMaterials: const {'cotton': 100},
            validateTitle: (_) => null,
            validateMaterialName: (_) => null,
            validateMaterialValue: (_) => null,
            onSelectClothingType: () {},
            onAddMaterial: () {},
            onRemoveMaterial: (_) {},
            onSubmit: () {},
            onReset: () {},
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('인식된 라벨 원문'), findsNothing);
  });

  testWidgets('목록 아이콘으로 고른 소재는 그 행에 한글 이름으로 들어가고, 닫힌 뒤 입력란이 다시 포커스를 받지 않는다', (
    tester,
  ) async {
    _usePhoneView(tester);
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'코': 100});
    addTearDown(materialInputs.dispose);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);
    await _pumpResultView(
      tester,
      materialInputs: materialInputs,
      materialCatalog: catalog,
    );

    final row = materialInputs[0];
    final nameField = find.widgetWithText(TextFormField, '코');
    await tester.ensureVisible(nameField);
    await tester.tap(nameField);
    await tester.pump();
    expect(row.nameFocusNode.hasFocus, isTrue);

    await tester.tap(find.byTooltip('목록에서 소재 고르기'));
    await tester.pumpAndSettle();
    expect(find.text('소재 선택'), findsOneWidget);

    await tester.tap(find.widgetWithText(ListTile, '면'));
    await tester.pumpAndSettle();

    expect(find.text('소재 선택'), findsNothing);
    expect(row.nameController.text, '면');
    // 포커스가 돌아오면 키보드와 추천 목록이 다시 뜬다.
    expect(row.nameFocusNode.hasFocus, isFalse);
  });

  testWidgets('선택창이 열린 동안 그 행이 지워지면 고른 소재를 쓰지 않는다', (tester) async {
    _usePhoneView(tester);
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'면': 60, '코': 40});
    addTearDown(materialInputs.dispose);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);
    final rebuildView = await _pumpResultView(
      tester,
      materialInputs: materialInputs,
      materialCatalog: catalog,
    );

    final pickerButtons = find.byTooltip('목록에서 소재 고르기');
    await tester.ensureVisible(pickerButtons.at(1));
    await tester.tap(pickerButtons.at(1));
    await tester.pumpAndSettle();

    rebuildView(() => materialInputs.removeAt(1));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ListTile, '비스코스'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(materialInputs.length, 1);
    expect(materialInputs[0].nameController.text, '면');
  });

  testWidgets('선택창이 열린 동안 앞 행이 지워져도 고른 소재는 원래 행에 들어간다', (tester) async {
    _usePhoneView(tester);
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'면': 60, '코': 40});
    addTearDown(materialInputs.dispose);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);
    final rebuildView = await _pumpResultView(
      tester,
      materialInputs: materialInputs,
      materialCatalog: catalog,
    );

    final targetRow = materialInputs[1];
    final pickerButtons = find.byTooltip('목록에서 소재 고르기');
    await tester.ensureVisible(pickerButtons.at(1));
    await tester.tap(pickerButtons.at(1));
    await tester.pumpAndSettle();

    rebuildView(() => materialInputs.removeAt(0));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ListTile, '비스코스'));
    await tester.pumpAndSettle();

    expect(materialInputs.length, 1);
    expect(identical(materialInputs[0], targetRow), isTrue);
    expect(targetRow.nameController.text, '비스코스');
  });

  testWidgets('소재명 오류 문구는 좁은 화면에서도 한 줄로 잘리지 않는다', (tester) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final materialInputs = MaterialInputCollection()..addEmpty();
    addTearDown(materialInputs.dispose);

    await _pumpResultView(
      tester,
      materialInputs: materialInputs,
      hasTriedSubmit: true,
      validateMaterialName: ScanFormValidator.validateMaterialName,
    );

    const message = '소재명을 입력해 주세요.';
    expect(find.text(message), findsOneWidget);
    expect(
      tester.renderObject<RenderParagraph>(find.text(message)).didExceedMaxLines,
      isFalse,
    );
  });

  testWidgets('입력란에 글자를 치면 기존 추천 목록이 뜨고, 고르면 한글 이름이 들어간다', (tester) async {
    _usePhoneView(tester);
    final materialInputs = MaterialInputCollection()..addEmpty();
    addTearDown(materialInputs.dispose);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);
    await _pumpResultView(
      tester,
      materialInputs: materialInputs,
      materialCatalog: catalog,
    );

    final nameField = find.widgetWithText(TextFormField, '소재명');
    await tester.ensureVisible(nameField);
    await tester.enterText(nameField, '코');
    await tester.pumpAndSettle();

    expect(find.text('면 (cotton)'), findsOneWidget);

    await tester.tap(find.text('면 (cotton)'));
    await tester.pumpAndSettle();

    expect(materialInputs[0].nameController.text, '면');
  });

  testWidgets('저장 중에는 소재 선택창 아이콘을 누를 수 없고, 카탈로그가 없으면 아이콘이 없다', (
    tester,
  ) async {
    _usePhoneView(tester);
    final materialInputs = MaterialInputCollection()
      ..setFromMaterials({'면': 100});
    addTearDown(materialInputs.dispose);
    final catalog = await _loadedCatalog();
    addTearDown(catalog.dispose);

    await _pumpResultView(
      tester,
      materialInputs: materialInputs,
      materialCatalog: catalog,
      isSaving: true,
    );
    final pickerButton = tester.widget<IconButton>(
      find.widgetWithIcon(IconButton, Icons.format_list_bulleted_rounded),
    );
    expect(pickerButton.onPressed, isNull);

    await _pumpResultView(tester, materialInputs: materialInputs);
    expect(find.byTooltip('목록에서 소재 고르기'), findsNothing);
  });
}

const _catalogItems = [
  MaterialCatalogItem(id: 1, nameKo: '면', nameEn: 'cotton', aliases: ['코튼']),
  MaterialCatalogItem(id: 2, nameKo: '비스코스', nameEn: 'viscose', aliases: []),
  MaterialCatalogItem(id: 3, nameKo: '울', nameEn: 'wool', aliases: ['모']),
];

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

/// 소재 선택창 테스트용으로 결과 화면을 띄웁니다.
/// 앱처럼 행을 지운 뒤 화면을 다시 그릴 수 있게 상태 갱신 함수를 돌려줍니다.
Future<StateSetter> _pumpResultView(
  WidgetTester tester, {
  required MaterialInputCollection materialInputs,
  MaterialCatalogController? materialCatalog,
  bool isSaving = false,
  bool hasTriedSubmit = false,
  FormFieldValidator<String>? validateMaterialName,
}) async {
  final titleController = TextEditingController(text: '새로 스캔한 의류');
  addTearDown(titleController.dispose);
  final formKey = GlobalKey<FormState>();
  late StateSetter rebuildView;

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: StatefulBuilder(
          builder: (context, setState) {
            rebuildView = setState;

            return ScanResultView(
              formKey: formKey,
              hasTriedSubmit: hasTriedSubmit,
              isSaving: isSaving,
              isScanFailed: false,
              titleController: titleController,
              selectedClothingType: ClothingTypeCatalog.defaultOption,
              materialInputs: materialInputs,
              materialCatalog: materialCatalog,
              scannedCare: '찬물 세탁',
              originalMaterials: const {},
              validateTitle: (_) => null,
              validateMaterialName: validateMaterialName ?? ((_) => null),
              validateMaterialValue: (_) => null,
              onSelectClothingType: () {},
              onAddMaterial: () {},
              onRemoveMaterial: (_) {},
              onSubmit: () {},
              onReset: () {},
            );
          },
        ),
      ),
    ),
  );

  // 저장 중에는 진행 표시가 계속 돌아 pumpAndSettle이 끝나지 않는다.
  if (isSaving) {
    await tester.pump();
  } else {
    await tester.pumpAndSettle();
  }
  return rebuildView;
}
