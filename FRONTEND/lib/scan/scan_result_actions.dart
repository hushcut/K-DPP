part of '../scan_screen.dart';

/// 분석 초안을 결과 폼에 반영하고 의류·소재 편집 상태를 관리합니다.
extension _ScanResultActions on _ScanScreenState {
  /// 분석 또는 수동 입력 초안을 화면 상태와 서버 원본 값에 반영합니다.
  void _applyScanDraft(
    ScanDraft draft, {
    bool isScanFailed = false,
    String? failureMessage,
  }) {
    unawaited(_loadMaterialCatalog());
    _setMaterialInputs(draft.materials);

    if (draft.isManualMaterialMode && draft.materials.isEmpty) {
      _materialInputs.addEmpty();
    }

    _updateState(() {
      _selectedClothingType = draft.clothingType;
      _selectedCategory = draft.category;
      _isScanComplete = true;
      _isScanFailed = isScanFailed;
      _isManualMaterialMode = draft.isManualMaterialMode;
      _scannedCare = draft.careInstruction;
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
      _selectedCategory = option.category;

      if (shouldReplaceTitle) {
        _titleController.text = option.defaultTitle;
      }
    });
  }

  Future<ClothingTypeOption?> _showClothingTypePicker({
    required ClothingTypeOption initialSelection,
    bool canDismiss = true,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final sheetColor = isDark ? const Color(0xFF121212) : Colors.white;

    return showModalBottomSheet<ClothingTypeOption>(
      context: context,
      isScrollControlled: true,
      isDismissible: canDismiss,
      enableDrag: true,
      showDragHandle: true,
      backgroundColor: sheetColor,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      clipBehavior: Clip.antiAlias,
      builder: (sheetContext) {
        return ClothingTypePickerSheet(
          options: ClothingTypeCatalog.options,
          initialSelection: initialSelection,
          onSelected: (option) {
            Navigator.pop(sheetContext, option);
          },
        );
      },
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

  /// 소재 컨트롤러 값이 바뀌면 해당 입력을 사용하는 결과 화면을 다시 그립니다.
  void _handleMaterialInputsChanged() {
    _updateState(() {});
  }

  /// 새 스캔을 위해 이미지·폼·서버 결과와 카메라 상태를 초기화합니다.
  void _resetScan() {
    _materialInputs.clear();

    _updateState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _isScanFailed = false;
      _isManualMaterialMode = false;
      _scannedCare = '';
      _scanFailureMessage = null;
      _originalScannedMaterials = const {};
      _serverHealth = null;
      _serverCarbonFootprint = null;
      _serverWeightGram = null;
      _serverCalculationMethod = null;
      _selectedClothingType = ClothingTypeCatalog.defaultOption;
      _selectedCategory = _selectedClothingType.category;
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
      _isSaving = false;
    });

    _cameraLifecycle.startIfNeeded();
  }
}
