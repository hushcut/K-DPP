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
            onMaterialInputsChanged: () {},
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
            onMaterialInputsChanged: () {},
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
}
