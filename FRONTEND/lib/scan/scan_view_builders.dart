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
    return ScanResultView(
      formKey: _formKey,
      hasTriedSubmit: _hasTriedSubmit,
      isSaving: _isSaving,
      isScanFailed: _isScanFailed,
      scanFailureMessage: _scanFailureMessage,
      titleController: _titleController,
      selectedClothingType: _selectedClothingType,
      materialInputs: _materialInputs,
      materialCatalog: _materialCatalog,
      scannedCare: _scannedCare,
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
      onReset: _resetScan,
    );
  }
}
