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
    } catch (error, stackTrace) {
      // 일시적인 실패가 앱 사용 내내 자동완성을 막지 않도록 다음 스캔에서 재시도합니다.
      _hasRequestedMaterialCatalog = false;
      debugPrint('소재 자동완성 목록을 불러오지 못했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
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
      _scanFailureMessage = null;
    });

    // 백엔드가 스캔 API에 인증을 요구해도 동작하도록 보유한 토큰을 함께 보냅니다.
    final accessToken = context.read<ClosetProvider>().accessToken;

    final outcome = await _scanAnalysisService.analyzeLabel(
      imageFile: imageFile,
      accessToken: accessToken,
    );

    if (!mounted) return;

    // 분석 중 다른 탭·화면으로 이동했다면 결과를 조용히 정리해,
    // 닫을 수 없는 유형 선택창이 엉뚱한 화면 위에 뜨지 않게 합니다.
    if (!widget.isActive) {
      _returnToScanView();
      return;
    }

    if (outcome is ScanAnalysisSuccess) {
      final result = outcome.result;
      final inferredType = _scanDraftService.inferInitialType(result);

      // _isScanning은 유형 선택이 끝날 때까지 유지해 대기 중 카메라 재초기화를 막습니다.
      _updateState(() {
        _selectedClothingType = inferredType;
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
      // 인증 만료는 수동 입력 대신 세션 정리 후 로그인으로 보내
      // 탄소 계산 경로의 401 처리와 정책을 맞춥니다.
      if (outcome.exception.type == ScanApiErrorType.unauthorized &&
          accessToken != null) {
        _updateState(() {
          _isScanning = false;
        });
        await SessionExpiryHandler.handle(context, message: outcome.userMessage);
        return;
      }

      await _showManualFallback(outcome.userMessage);
    }
  }

  /// 자동 분석에 실패해도 유형과 소재를 직접 입력할 수 있는 초안을 만듭니다.
  /// _isScanning은 유형 선택이 끝날 때까지 유지해 카메라 재초기화를 막습니다.
  Future<void> _showManualFallback(String message) async {
    if (!mounted) return;

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
    if (_isScanning || _isPickingImage) return;

    final captureResult = await _scanCaptureService.captureFromCamera(
      cameraSession: _cameraSession,
    );

    if (!mounted) {
      // 화면이 사라졌어도 방금 촬영된 임시 파일은 캐시에 남기지 않고 정리합니다.
      if (captureResult
          case ScanCaptureSelected(
            :final imageFile,
            shouldDeleteAfterAnalysis: true,
          )) {
        await _scanCaptureService.deleteTemporaryCaptureFile(imageFile);
      }
      return;
    }

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
        // 카메라 해제를 기다리는 사이 앨범 버튼으로 두 번째 스캔이
        // 겹치지 않도록 먼저 잠급니다.
        _updateState(() {
          _isScanning = true;
        });

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
    if (_isScanning || _isPickingImage) return;

    // 앨범 선택 잠금은 카메라 사용 조건과 분리해, 혹시 잠금이 남더라도
    // 카메라가 다시 켜지는 것을 막지 않도록 합니다.
    _isPickingImage = true;

    final ScanCaptureResult captureResult;

    try {
      await _cameraLifecycle.disposeCamera();

      if (!mounted) return;

      captureResult = await _scanCaptureService.pickFromGallery();
    } finally {
      // 예외로 끝나더라도 앨범 버튼이 영구히 잠기지 않게 합니다.
      _isPickingImage = false;
    }

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
