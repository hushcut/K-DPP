part of '../scan_screen.dart';

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

  /// 스캔 직후 반드시 고르는 종류 선택 화면을 엽니다. "<"(다시 촬영)로 나가면 null을 반환합니다.
  /// [confirmRetake]는 나가기 전에 분석 결과가 사라진다고 물을지, [failureMessage]는 화면 맨 위에
  /// 보일 분석 실패 이유입니다.
  Future<ClothingTypeOption?> _showClothingTypePicker({
    required ClothingTypeOption initialSelection,
    required bool confirmRetake,
    String? failureMessage,
  }) {
    return showClothingTypePickerScreen(
      context: context,
      options: _clothingTypeCatalog.value,
      optionsListenable: _clothingTypeCatalog,
      initialSelection: initialSelection,
      confirmRetake: confirmRetake,
      failureMessage: failureMessage,
    );
  }

  /// 결과 입력 중 종류를 바꾸는 것은 가벼운 선택이라 시트로 엽니다(DECISIONS 226 ⑥).
  Future<void> _selectClothingTypeFromResult() async {
    final picked = await showClothingTypePickerSheet(
      context: context,
      options: _clothingTypeCatalog.value,
      optionsListenable: _clothingTypeCatalog,
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

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final shouldDiscard = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          backgroundColor: palette.card,
          title: Text(
            '작성 중인 내용을 버릴까요?',
            style: TextStyle(color: palette.textPrimary),
          ),
          content: Text(
            '스캔 화면을 닫으면 지금까지 입력한 내용이 사라져요.',
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
              child: const Text(
                '버리고 닫기',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );

    if (shouldDiscard != true || !mounted) return;

    Navigator.pop(context);
  }

  /// 새 스캔을 위해 이미지·폼·서버 결과와 카메라 상태를 초기화합니다.
  void _resetScan() {
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

    _cameraLifecycle.startIfNeeded();
  }
}
