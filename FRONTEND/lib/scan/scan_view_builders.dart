part of '../scan_screen.dart';

/// 스캔 상태를 촬영 화면 또는 결과 편집 화면으로 조립합니다.
extension _ScanViewBuilders on _ScanScreenState {
  Widget _buildScanScreen() {
    return _isScanComplete ? _buildResultView() : _buildCameraView();
  }

  Widget _buildCameraView() {
    return ScanCameraView(
      cameraController: _cameraSession.controller,
      selectedImage: _selectedImage,
      isScanning: _isScanning,
      isCameraInitializing: _cameraSession.isInitializing,
      cameraErrorMessage: _cameraSession.errorMessage,
      onRetryCamera: _cameraLifecycle.initialize,
      onPickFromGallery: _pickFromGallery,
      onTakePicture: _takePicture,
    );
  }

  /// 현재 상태와 콜백을 표시 전용 결과 위젯에 전달합니다.
  Widget _buildResultView() {
    final closet = Provider.of<ClosetProvider>(context);

    return ScanResultView(
      // 로그인 상태면 저장할 때 서버가 계산하므로 미리보기 숫자(앱 소재표 기준)를 보이지
      // 않습니다. 세션이 만료됐으면 앱 추정값으로 저장하니 미리보기 숫자가 맞습니다.
      carbonCalculatedOnSave:
          closet.accessToken != null && closet.isAuthenticated,
      // 로그인 계정의 저장 길(서버 계산·끊김·세션 만료)은 모두 서버 공개 계수로 판정합니다.
      checksPublicFactors: closet.accessToken != null,
      formKey: _formKey,
      hasTriedSubmit: _hasTriedSubmit,
      isSaving: _isSaving,
      isScanFailed: _isScanFailed,
      scanFailureMessage: _scanFailureMessage,
      scanNotices: _scanNotices,
      unsupportedMaterials: _scanUnsupportedMaterials,
      titleController: _titleController,
      selectedClothingType: _selectedClothingType,
      materialInputs: _materialInputs,
      materialCatalog: _materialCatalog,
      scannedCare: _scannedCare,
      rawOcrPreview: _scannedOcrPreview,
      originalMaterials: _originalScannedMaterials,
      serverHealth: _serverHealth,
      serverCarbonFootprint: _serverCarbonFootprint,
      serverWeightGram: _serverWeightGram,
      serverCalculationMethod: _serverCalculationMethod,
      validateTitle: ScanFormValidator.validateTitle,
      validateMaterialName: ScanFormValidator.validateMaterialName,
      validateMaterialValue: ScanFormValidator.validateMaterialValue,
      onSelectClothingType: () {
        _selectClothingTypeFromResult();
      },
      onAddMaterial: _addMaterialInput,
      onRemoveMaterial: _removeMaterialInput,
      onSubmit: () {
        _submitClothes();
      },
      onReset: () {
        _confirmRetake();
      },
    );
  }
}
