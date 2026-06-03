import 'dart:io';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothing_type_option.dart';
import 'services/scan_analysis_service.dart';
import 'services/scan_camera_lifecycle_service.dart';
import 'services/scan_camera_session.dart';
import 'services/scan_capture_service.dart';
import 'services/scan_draft_service.dart';
import 'services/scan_save_service.dart';
import 'utils/clothing_type_catalog.dart';
import 'utils/scan_form_validator.dart';
import 'widgets/clothing_type_picker_sheet.dart';
import 'widgets/material_input_collection.dart';
import 'widgets/scan_camera_view.dart';
import 'widgets/scan_result_view.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key, this.isActive = true});

  final bool isActive;

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> with WidgetsBindingObserver {
  bool _isScanning = false;
  bool _isScanComplete = false;
  bool _hasTriedSubmit = false;
  bool _isManualMaterialMode = false;

  File? _selectedImage;

  final ScanAnalysisService _scanAnalysisService = const ScanAnalysisService();
  final ScanCaptureService _scanCaptureService = ScanCaptureService();
  final ScanDraftService _scanDraftService = const ScanDraftService();
  final ScanSaveService _scanSaveService = const ScanSaveService();
  final ScanCameraSession _cameraSession = ScanCameraSession();
  late final ScanCameraLifecycleService _cameraLifecycle;

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  String _scannedCare = '';

  final MaterialInputCollection _materialInputs = MaterialInputCollection();
  final TextEditingController _titleController = TextEditingController();

  ClothingTypeOption _selectedClothingType = ClothingTypeCatalog.defaultOption;
  String _selectedCategory = ClothingTypeCatalog.defaultOption.category;

  @override
  void initState() {
    super.initState();
    _cameraLifecycle = ScanCameraLifecycleService(
      canUseCamera: _canUseCamera,
      isCameraReady: () => _cameraSession.isReady,
      initializeCamera: _cameraSession.initialize,
      disposeCamera: _cameraSession.disposeCamera,
    );
    WidgetsBinding.instance.addObserver(this);
    _cameraSession.addListener(_handleCameraSessionChanged);
    _titleController.text = '새로 스캔한 의류';

    if (widget.isActive) {
      _cameraLifecycle.initialize();
    }
  }

  @override
  void didUpdateWidget(covariant ScanScreen oldWidget) {
    super.didUpdateWidget(oldWidget);

    _cameraLifecycle.handleActiveChanged(
      wasActive: oldWidget.isActive,
      isActive: widget.isActive,
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _cameraLifecycle.handleAppLifecycleState(state);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cameraSession.removeListener(_handleCameraSessionChanged);
    _cameraSession.dispose();
    _materialInputs.dispose();
    _titleController.dispose();
    super.dispose();
  }

  void _handleCameraSessionChanged() {
    if (!mounted) return;
    setState(() {});
  }

  bool _canUseCamera() {
    return mounted && widget.isActive && !_isScanComplete && !_isScanning;
  }

  Future<void> _scanImageFile(File imageFile) async {
    setState(() {
      _selectedImage = imageFile;
      _isScanning = true;
      _isScanComplete = false;
      _hasTriedSubmit = false;
      _isManualMaterialMode = false;
    });

    final outcome = await _scanAnalysisService.analyzeLabel(
      imageFile: imageFile,
    );

    if (!mounted) return;

    if (outcome is ScanAnalysisSuccess) {
      final result = outcome.result;
      final inferredType = _scanDraftService.inferInitialType(result);

      setState(() {
        _isScanning = false;
        _selectedClothingType = inferredType;
        _selectedCategory = inferredType.category;
      });

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

  Future<void> _showManualFallback(String message) async {
    if (!mounted) return;

    setState(() {
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

    _applyScanDraft(_scanDraftService.buildManual(clothingType: selectedType));

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  void _returnToScanView() {
    _materialInputs.clear();

    setState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _isManualMaterialMode = false;
      _scannedCare = '';
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
    });

    _cameraLifecycle.startIfNeeded();
  }

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

  void _applyScanDraft(ScanDraft draft) {
    _setMaterialInputs(draft.materials);

    setState(() {
      _selectedClothingType = draft.clothingType;
      _selectedCategory = draft.category;
      _isScanComplete = true;
      _isManualMaterialMode = draft.isManualMaterialMode;
      _scannedCare = draft.careInstruction;
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

  void _applyClothingType(ClothingTypeOption option) {
    final shouldReplaceTitle = _shouldReplaceTitleWithType(
      _titleController.text,
    );

    setState(() {
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

  void _setMaterialInputs(Map<String, double> materials) {
    _materialInputs.setFromMaterials(materials);
  }

  void _addMaterialInput() {
    setState(() {
      _materialInputs.addEmpty();
    });
  }

  void _removeMaterialInput(int index) {
    setState(() {
      _materialInputs.removeAt(index);
    });
  }

  void _syncMaterialInputs() {
    setState(() {});
  }

  Future<void> _submitClothes() async {
    setState(() {
      _hasTriedSubmit = true;
    });

    final isFormValid = _formKey.currentState?.validate() ?? false;

    if (!isFormValid) return;

    final editedMaterials = _materialInputs.collectEditedMaterials();

    final saveResult = _scanSaveService.buildClothes(
      title: _titleController.text,
      category: _selectedCategory,
      materials: editedMaterials,
      careInstruction: _scannedCare,
      clothingType: _selectedClothingType,
    );

    switch (saveResult) {
      case ScanSaveFailure(:final message):
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
        return;
      case ScanSaveSuccess(:final clothes):
        await Provider.of<ClosetProvider>(
          context,
          listen: false,
        ).addClothes(clothes);

        if (!mounted) return;

        Navigator.pushReplacementNamed(context, '/report', arguments: clothes);
    }
  }

  void _resetScan() {
    _materialInputs.clear();

    setState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _isManualMaterialMode = false;
      _scannedCare = '';
      _selectedClothingType = ClothingTypeCatalog.defaultOption;
      _selectedCategory = _selectedClothingType.category;
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
    });

    _cameraLifecycle.startIfNeeded();
  }

  @override
  Widget build(BuildContext context) {
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

  Future<void> _selectClothingTypeFromResult() async {
    final picked = await _showClothingTypePicker(
      initialSelection: _selectedClothingType,
    );

    if (!mounted || picked == null) return;

    _applyClothingType(picked);
  }

  Widget _buildResultView() {
    return ScanResultView(
      formKey: _formKey,
      hasTriedSubmit: _hasTriedSubmit,
      isManualMaterialMode: _isManualMaterialMode,
      titleController: _titleController,
      selectedClothingType: _selectedClothingType,
      materialInputs: _materialInputs,
      scannedCare: _scannedCare,
      validateTitle: ScanFormValidator.validateTitle,
      validateMaterialName: ScanFormValidator.validateMaterialName,
      validateMaterialValue: ScanFormValidator.validateMaterialValue,
      onSelectClothingType: () {
        _selectClothingTypeFromResult();
      },
      onAddMaterial: _addMaterialInput,
      onRemoveMaterial: _removeMaterialInput,
      onSyncMaterialInputs: _syncMaterialInputs,
      onSubmit: () {
        _submitClothes();
      },
      onReset: _resetScan,
    );
  }
}
