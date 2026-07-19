part of '../scan_screen.dart';

/// 이미지 획득, 라벨 분석, 수동 입력 전환까지 촬영 흐름을 처리합니다.
extension _ScanCaptureActions on _ScanScreenState {
  /// 결과 편집에 쓰는 소재 자동완성 목록을 최초 한 번만 요청합니다.
  Future<void> _loadMaterialCatalog() async {
    if (_hasRequestedMaterialCatalog) return;

    _hasRequestedMaterialCatalog = true;

    try {
      final catalog = await _materialCatalogApiService.fetchMaterials();

      if (!mounted) return;

      _updateState(() {
        _materialCatalog = catalog;
      });
    } catch (error) {
      debugPrint('소재 자동완성 목록을 불러오지 못했습니다: $error');
    }
  }

  /// 선택 이미지를 분석하고 의류 유형 확인 후 편집 가능한 초안으로 변환합니다.
  Future<void> _scanImageFile(File imageFile) async {
    _updateState(() {
      _selectedImage = imageFile;
      _isScanning = true;
      _isScanComplete = false;
      _isScanFailed = false;
      _hasTriedSubmit = false;
      _isSaving = false;
      _isManualMaterialMode = false;
      _scanFailureMessage = null;
    });

    final outcome = await _scanAnalysisService.analyzeLabel(
      imageFile: imageFile,
    );

    if (!mounted) return;

    if (outcome is ScanAnalysisSuccess) {
      final result = outcome.result;
      final inferredType = _scanDraftService.inferInitialType(result);

      _updateState(() {
        _isScanning = false;
        _selectedClothingType = inferredType;
        _selectedCategory = inferredType.category;
      });

      // 무게 범위와 분류를 확정할 수 있도록 분석 유형을 사용자에게 확인받습니다.
      final selectedType = await _showClothingTypePicker(
        initialSelection: inferredType,
        canDismiss: false,
      );

      if (!mounted) return;

      if (selectedType == null) {
        _returnToScanView();
        return;
      }

      _applyScanDraft(
        _scanDraftService.buildFromResult(
          result: result,
          clothingType: selectedType,
        ),
      );
      return;
    }

    if (outcome is ScanAnalysisFailure) {
      await _showManualFallback(outcome.userMessage);
    }
  }

  /// 자동 분석에 실패해도 유형과 소재를 직접 입력할 수 있는 초안을 만듭니다.
  Future<void> _showManualFallback(String message) async {
    if (!mounted) return;

    _updateState(() {
      _isScanning = false;
    });

    final selectedType = await _showClothingTypePicker(
      initialSelection: _selectedClothingType,
      canDismiss: false,
    );

    if (!mounted) return;

    if (selectedType == null) {
      _returnToScanView();
      return;
    }

    _applyScanDraft(
      _scanDraftService.buildManual(clothingType: selectedType),
      isScanFailed: true,
      failureMessage: message,
    );

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  /// 유형 선택 취소 시 분석 상태를 지우고 카메라 화면으로 돌아갑니다.
  void _returnToScanView() {
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
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
    });

    _cameraLifecycle.startIfNeeded();
  }

  /// 카메라 촬영 결과를 분기하고 임시 파일은 분석이 끝난 뒤 정리합니다.
  Future<void> _takePicture() async {
    if (_isScanning) return;

    final captureResult = await _scanCaptureService.captureFromCamera(
      cameraSession: _cameraSession,
    );

    if (!mounted) return;

    switch (captureResult) {
      case ScanCaptureBlocked(:final message):
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));

        await _cameraLifecycle.initialize();
        return;

      case ScanCaptureBusy():
        return;

      case ScanCaptureCancelled():
        return;

      case ScanCaptureFailure(:final message):
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
        return;

      case ScanCaptureSelected(
        :final imageFile,
        :final shouldDeleteAfterAnalysis,
      ):
        await _cameraLifecycle.disposeCamera();

        try {
          await _scanImageFile(imageFile);
        } finally {
          if (shouldDeleteAfterAnalysis) {
            await _scanCaptureService.deleteTemporaryCaptureFile(imageFile);
          }
        }
    }
  }

  /// 카메라를 잠시 해제한 뒤 앨범 이미지를 같은 분석 흐름으로 전달합니다.
  Future<void> _pickFromGallery() async {
    if (_isScanning) return;

    await _cameraLifecycle.disposeCamera();

    if (!mounted) return;

    final captureResult = await _scanCaptureService.pickFromGallery();

    if (!mounted) return;

    switch (captureResult) {
      case ScanCaptureSelected(:final imageFile):
        await _scanImageFile(imageFile);
        return;

      case ScanCaptureCancelled():
        _cameraLifecycle.startIfNeeded();
        return;

      case ScanCaptureFailure(:final message):
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
        _cameraLifecycle.startIfNeeded();
        return;

      case ScanCaptureBlocked():
      case ScanCaptureBusy():
        _cameraLifecycle.startIfNeeded();
        return;
    }
  }
}
