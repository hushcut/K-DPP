part of '../scan_screen.dart';

/// 결과 폼에서 사용자가 고칠 수 있는 값(제목·의류 종류·소재 행 글자)을 비교용으로 모은 모습입니다.
typedef _ResultFormSnapshot = ({
  String title,
  Object clothingType,
  List<(String, String)> materialRows,
});

/// 분석 초안을 결과 폼에 반영하고 의류·소재 편집 상태를 관리합니다.
extension _ScanResultActions on _ScanScreenState {
  /// 분석 또는 수동 입력 초안을 화면 상태와 서버 원본 값에 반영합니다.
  void _applyScanDraft(
    ScanDraft draft, {
    bool isScanFailed = false,
    String? failureMessage,
  }) {
    // 결과 편집에 쓰는 소재 목록은 처음 한 번만 받고, 실패했으면 이때 다시 요청합니다.
    unawaited(_materialCatalog.load());
    _setMaterialInputs(draft.materials);

    if (draft.isManualMaterialMode && draft.materials.isEmpty) {
      _materialInputs.addEmpty();
    }

    _updateState(() {
      _selectedClothingType = draft.clothingType;
      _isScanning = false;
      _isScanComplete = true;
      _isScanFailed = isScanFailed;
      _scannedCare = draft.careInstruction;
      _scannedOcrPreview = draft.rawOcrPreview;
      _scanFailureMessage = failureMessage;
      _originalScannedMaterials = Map.unmodifiable(draft.materials);
      _serverHealth = draft.serverHealth;
      _serverCarbonFootprint = draft.serverCarbonFootprint;
      _serverWeightGram = draft.serverWeightGram;
      _serverCalculationMethod = draft.serverCalculationMethod;
      _titleController.text = draft.title;
      _hasTriedSubmit = false;
    });

    _initialResultForm = _captureResultForm();
  }

  _ResultFormSnapshot _captureResultForm() => (
    title: _titleController.text,
    clothingType: _clothingTypeKey(_selectedClothingType),
    materialRows: [
      for (var i = 0; i < _materialInputs.length; i++)
        (
          _materialInputs[i].nameController.text,
          _materialInputs[i].percentController.text,
        ),
    ],
  );

  // 같은 종류를 다시 고르면(서버 무게표가 늦게 와 다른 객체여도) 고친 것으로 보지 않게 값으로 비교합니다.
  Object _clothingTypeKey(ClothingTypeOption option) => (
    option.id,
    option.label,
    option.category,
    option.minWeightGram,
    option.maxWeightGram,
    option.estimatedWeightGram,
    option.isDirectWeight,
  );

  /// 결과 폼을 채운 뒤 사용자가 제목·종류·소재를 고쳤는지입니다. 고쳤다가 처음 글자로
  /// 되돌렸으면 고치지 않은 것으로 봅니다.
  bool get _hasEditedResultForm {
    final initial = _initialResultForm;
    if (initial == null) return false;

    final current = _captureResultForm();
    return current.title != initial.title ||
        current.clothingType != initial.clothingType ||
        !listEquals(current.materialRows, initial.materialRows);
  }

  bool _shouldReplaceTitleWithType(String title) {
    final trimmed = title.trim();

    if (trimmed.isEmpty || trimmed == '새로 스캔한 의류') {
      return true;
    }

    if (_selectedClothingType.defaultTitle == trimmed) {
      return true;
    }

    return ClothingTypeCatalog.hasDefaultTitle(trimmed);
  }

  /// 사용자가 이름을 바꾸지 않은 경우에만 유형의 기본 이름을 적용합니다.
  void _applyClothingType(ClothingTypeOption option) {
    final shouldReplaceTitle = _shouldReplaceTitleWithType(
      _titleController.text,
    );

    _updateState(() {
      _selectedClothingType = option;

      if (shouldReplaceTitle) {
        _titleController.text = option.defaultTitle;
      }
    });
  }

  /// [discardPrompt]를 주면 선택을 건너뛸 수 없고, '다시 촬영' 확인 후에만 null을 반환합니다.
  /// [failureMessage]는 분석 실패 이유로, 시트 맨 위에 보입니다.
  Future<ClothingTypeOption?> _showClothingTypePicker({
    required ClothingTypeOption initialSelection,
    ClothingTypePickerDiscardPrompt? discardPrompt,
    String? failureMessage,
  }) {
    return showClothingTypePickerSheet(
      context: context,
      options: _clothingTypeCatalog.value,
      optionsListenable: _clothingTypeCatalog,
      initialSelection: initialSelection,
      discardPrompt: discardPrompt,
      failureMessage: failureMessage,
    );
  }

  Future<void> _selectClothingTypeFromResult() async {
    final picked = await _showClothingTypePicker(
      initialSelection: _selectedClothingType,
    );

    if (!mounted || picked == null) return;

    _applyClothingType(picked);
  }

  void _setMaterialInputs(Map<String, double> materials) {
    _materialInputs.setFromMaterials(materials);
  }

  void _addMaterialInput() {
    _updateState(() {
      _materialInputs.addEmpty();
    });
  }

  void _removeMaterialInput(int index) {
    _updateState(() {
      _materialInputs.removeAt(index);
    });
  }


  /// 결과 입력 중 닫으려 하면 버릴지 묻고, 버리기로 한 경우에만 스캔 화면을 닫습니다.
  /// 저장 중에는 끝나면 리포트로 넘어가므로 묻지 않고 그대로 둡니다.
  Future<void> _confirmDiscardAndClose() async {
    if (_isSaving) return;

    final shouldDiscard = await _askDiscardInput(
      title: '작성 중인 내용을 버릴까요?',
      message: '스캔 화면을 닫으면 지금까지 입력한 내용이 사라져요.',
      discardLabel: '버리고 닫기',
    );

    if (!shouldDiscard || !mounted) return;

    Navigator.pop(context);
  }

  /// 결과 화면 '다시 촬영': 입력을 고쳤으면 버릴지 묻고, 스캔 직후 그대로면 묻지 않고
  /// 촬영 화면으로 돌아갑니다(DECISIONS 2026-10-14 C24).
  Future<void> _confirmRetake() async {
    if (_hasEditedResultForm) {
      final shouldRetake = await _askDiscardInput(
        title: '다시 촬영할까요?',
        message: '다시 촬영하면 지금까지 입력한 내용이 사라져요.',
        discardLabel: '다시 촬영',
      );

      if (!shouldRetake || !mounted) return;
    }

    _resetScan();
  }

  /// 입력을 버릴지 묻고, [discardLabel] 버튼을 골랐을 때만 true 를 돌려줍니다.
  Future<bool> _askDiscardInput({
    required String title,
    required String message,
    required String discardLabel,
  }) async {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final shouldDiscard = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(title, style: TextStyle(color: palette.textPrimary)),
          content: Text(
            message,
            style: TextStyle(
              height: 1.5,
              color: isDark ? const Color(0xFFD1D1D6) : const Color(0xFF444444),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('계속 작성하기'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.redAccent,
              ),
              child: Text(
                discardLabel,
                style: const TextStyle(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );

    return shouldDiscard == true;
  }

  /// 새 스캔을 위해 이미지·폼·서버 결과와 카메라 상태를 초기화합니다.
  void _resetScan() {
    _clearScanResult();
    _cameraLifecycle.startIfNeeded();
  }

  /// 이미지·폼·서버 결과를 지워 촬영 화면 상태로 되돌립니다. 카메라는 켜지 않습니다 — 저장 직후엔
  /// 곧바로 리포트가 위에 쌓이고, 리포트가 닫혀 이 화면이 다시 보일 때 켭니다.
  void _clearScanResult() {
    _materialInputs.clear();

    _updateState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _isScanFailed = false;
      _scannedCare = '';
      _scanFailureMessage = null;
      _originalScannedMaterials = const {};
      _serverHealth = null;
      _serverCarbonFootprint = null;
      _serverWeightGram = null;
      _serverCalculationMethod = null;
      _selectedClothingType = ClothingTypeCatalog.defaultOption;
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
      _isSaving = false;
    });
  }
}
