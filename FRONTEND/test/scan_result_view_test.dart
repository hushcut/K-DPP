import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
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

    var parentBuildCount = 0;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) {
              parentBuildCount++;
              return ScanResultView(
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
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final buildsAfterFirstFrame = parentBuildCount;
    expect(find.text('현재 소재 합계: 70.0%'), findsOneWidget);

    // 함유율 필드에 입력하면 합계 표시는 바뀌지만 상위 빌드는 늘지 않아야 합니다.
    await tester.enterText(find.text('70'), '100');
    await tester.pumpAndSettle();

    expect(find.text('현재 소재 합계: 100.0%'), findsOneWidget);
    expect(parentBuildCount, buildsAfterFirstFrame);
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
}
