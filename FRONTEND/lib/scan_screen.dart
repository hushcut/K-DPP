import 'dart:io';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'models/clothes.dart';
import 'models/scan_result.dart';
import 'services/scan_api_service.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  static const List<_ClothingTypeOption> _clothingTypeOptions = [
    _ClothingTypeOption(
      label: '반팔 티셔츠',
      category: '상의',
      weightRangeLabel: '100~250g',
      estimatedWeightGram: 180,
      icon: Icons.checkroom_outlined,
    ),
    _ClothingTypeOption(
      label: '셔츠 / 블라우스',
      category: '상의',
      weightRangeLabel: '150~350g',
      estimatedWeightGram: 240,
      icon: Icons.dry_cleaning_outlined,
    ),
    _ClothingTypeOption(
      label: '긴팔 / 맨투맨',
      category: '상의',
      weightRangeLabel: '350~750g',
      estimatedWeightGram: 520,
      icon: Icons.checkroom_outlined,
    ),
    _ClothingTypeOption(
      label: '니트',
      category: '상의',
      weightRangeLabel: '400~900g',
      estimatedWeightGram: 620,
      icon: Icons.texture_outlined,
    ),
    _ClothingTypeOption(
      label: '바지',
      category: '하의',
      weightRangeLabel: '450~900g',
      estimatedWeightGram: 680,
      icon: Icons.accessibility_new_outlined,
    ),
    _ClothingTypeOption(
      label: '스커트',
      category: '하의',
      weightRangeLabel: '250~650g',
      estimatedWeightGram: 420,
      icon: Icons.accessibility_new_outlined,
    ),
    _ClothingTypeOption(
      label: '원피스',
      category: '상의',
      weightRangeLabel: '350~850g',
      estimatedWeightGram: 560,
      icon: Icons.woman_outlined,
    ),
    _ClothingTypeOption(
      label: '아우터',
      category: '상의',
      weightRangeLabel: '800~1800g',
      estimatedWeightGram: 1200,
      icon: Icons.ac_unit_outlined,
    ),
    _ClothingTypeOption(
      label: '직접 입력',
      category: '상의',
      weightRangeLabel: '실제 무게 입력',
      estimatedWeightGram: 500,
      icon: Icons.scale_outlined,
      isDirectWeightPlaceholder: true,
    ),
  ];

  bool _isScanning = false;
  bool _isScanComplete = false;
  bool _hasTriedSubmit = false;
  bool _isCameraInitializing = true;
  bool _isManualMaterialMode = false;

  String? _cameraErrorMessage;
  File? _selectedImage;
  CameraController? _cameraController;

  final ImagePicker _picker = ImagePicker();
  final ScanApiService _scanApiService = const ScanApiService();

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  Map<String, double> _scannedMaterials = {};
  String _scannedCare = '';

  final List<_MaterialEditController> _materialInputs = [];
  final TextEditingController _titleController = TextEditingController();

  _ClothingTypeOption _selectedClothingType = _clothingTypeOptions.first;
  String _selectedCategory = '상의';

  @override
  void initState() {
    super.initState();
    _titleController.text = '새로 스캔한 의류';
    _initializeCamera();
  }

  @override
  void dispose() {
    _cameraController?.dispose();
    _disposeMaterialInputs();
    _titleController.dispose();
    super.dispose();
  }

  Future<void> _initializeCamera() async {
    setState(() {
      _isCameraInitializing = true;
      _cameraErrorMessage = null;
    });

    try {
      final cameras = await availableCameras();

      if (cameras.isEmpty) {
        throw Exception('사용 가능한 카메라가 없습니다.');
      }

      final backCamera = cameras.firstWhere(
            (camera) => camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );

      final controller = CameraController(
        backCamera,
        ResolutionPreset.high,
        enableAudio: false,
      );

      await controller.initialize();

      if (!mounted) {
        await controller.dispose();
        return;
      }

      final oldController = _cameraController;
      _cameraController = controller;
      await oldController?.dispose();

      setState(() {
        _isCameraInitializing = false;
        _cameraErrorMessage = null;
      });
    } catch (e) {
      debugPrint('카메라 초기화 실패: $e');

      if (!mounted) return;

      setState(() {
        _isCameraInitializing = false;
        _cameraErrorMessage = '카메라를 불러올 수 없어요.\n카메라 권한을 확인해 주세요.';
      });
    }
  }

  Future<void> _scanImageFile(File imageFile) async {
    setState(() {
      _selectedImage = imageFile;
      _isScanning = true;
      _isScanComplete = false;
      _hasTriedSubmit = false;
      _isManualMaterialMode = false;
    });

    try {
      final ScanResult result =
      await _scanApiService.scanLabel(imageFile: imageFile);

      if (!mounted) return;

      final inferredType = _inferTypeFromCategory(result.category);

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

      _setMaterialInputs(result.materials);

      setState(() {
        _selectedClothingType = selectedType;
        _selectedCategory = selectedType.category;
        _isScanComplete = true;
        _isManualMaterialMode = false;
        _scannedMaterials = result.materials;
        _scannedCare = result.careInstruction;
        _titleController.text = (result.title?.trim().isNotEmpty ?? false)
            ? result.title!.trim()
            : selectedType.defaultTitle;
      });
    } on ScanApiException catch (e) {
      await _showManualFallback(e);
    } catch (e) {
      debugPrint('예상하지 못한 스캔 오류: $e');
      await _showManualFallback(
        ScanApiException(
          type: ScanApiErrorType.unknown,
          message: e.toString(),
        ),
      );
    }
  }

  Future<void> _showManualFallback(ScanApiException exception) async {
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

    _setMaterialInputs({});

    setState(() {
      _selectedClothingType = selectedType;
      _selectedCategory = selectedType.category;
      _isScanComplete = true;
      _isManualMaterialMode = true;
      _scannedMaterials = {};
      _scannedCare = '라벨의 세탁 지침을 확인해 주세요.';
      _titleController.text = selectedType.defaultTitle;
      _hasTriedSubmit = false;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(exception.userMessage)),
    );
  }

  void _returnToScanView() {
    setState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _isManualMaterialMode = false;
      _scannedMaterials = {};
      _scannedCare = '';
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
    });
  }

  Future<void> _takePicture() async {
    if (_isScanning) return;

    final controller = _cameraController;

    if (controller == null || !controller.value.isInitialized) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('카메라를 준비하고 있어요. 잠시 후 다시 시도해 주세요.')),
      );

      await _initializeCamera();
      return;
    }

    if (controller.value.isTakingPicture) return;

    try {
      final image = await controller.takePicture();
      await _scanImageFile(File(image.path));
    } catch (e) {
      debugPrint('사진 촬영 실패: $e');

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('사진을 촬영하지 못했어요. 다시 시도해 주세요.')),
      );
    }
  }

  Future<void> _pickFromGallery() async {
    if (_isScanning) return;

    final XFile? image = await _picker.pickImage(source: ImageSource.gallery);

    if (image == null) return;

    await _scanImageFile(File(image.path));
  }

  _ClothingTypeOption _inferTypeFromCategory(String? category) {
    final text = category?.toLowerCase().trim() ?? '';

    if (text.contains('아우터') ||
        text.contains('outer') ||
        text.contains('jacket') ||
        text.contains('coat')) {
      return _clothingTypeOptions.firstWhere((item) => item.label == '아우터');
    }

    if (text.contains('니트') || text.contains('knit')) {
      return _clothingTypeOptions.firstWhere((item) => item.label == '니트');
    }

    if (text.contains('바지') ||
        text.contains('하의') ||
        text.contains('pants') ||
        text.contains('bottom')) {
      return _clothingTypeOptions.firstWhere((item) => item.label == '바지');
    }

    if (text.contains('스커트') || text.contains('skirt')) {
      return _clothingTypeOptions.firstWhere((item) => item.label == '스커트');
    }

    if (text.contains('원피스') || text.contains('dress')) {
      return _clothingTypeOptions.firstWhere((item) => item.label == '원피스');
    }

    if (text.contains('셔츠') ||
        text.contains('블라우스') ||
        text.contains('shirt') ||
        text.contains('blouse')) {
      return _clothingTypeOptions.firstWhere(
            (item) => item.label == '셔츠 / 블라우스',
      );
    }

    if (text.contains('맨투맨') ||
        text.contains('긴팔') ||
        text.contains('sweatshirt')) {
      return _clothingTypeOptions.firstWhere(
            (item) => item.label == '긴팔 / 맨투맨',
      );
    }

    return _clothingTypeOptions.first;
  }

  bool _shouldReplaceTitleWithType(String title) {
    final trimmed = title.trim();

    if (trimmed.isEmpty || trimmed == '새로 스캔한 의류') {
      return true;
    }

    if (_selectedClothingType.defaultTitle == trimmed) {
      return true;
    }

    return _clothingTypeOptions.any((option) => option.defaultTitle == trimmed);
  }

  void _applyClothingType(_ClothingTypeOption option) {
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

  Future<_ClothingTypeOption?> _showClothingTypePicker({
    required _ClothingTypeOption initialSelection,
    bool canDismiss = true,
  }) {
    return showModalBottomSheet<_ClothingTypeOption>(
      context: context,
      isScrollControlled: true,
      isDismissible: canDismiss,
      enableDrag: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return _ClothingTypePickerSheet(
          options: _clothingTypeOptions,
          initialSelection: initialSelection,
          onSelected: (option) {
            Navigator.pop(sheetContext, option);
          },
        );
      },
    );
  }

  void _disposeMaterialInputs() {
    for (final item in _materialInputs) {
      item.dispose();
    }

    _materialInputs.clear();
  }

  void _setMaterialInputs(Map<String, double> materials) {
    _disposeMaterialInputs();

    materials.forEach((key, value) {
      _materialInputs.add(
        _MaterialEditController(
          name: key,
          percent: value,
        ),
      );
    });
  }

  void _addMaterialInput() {
    setState(() {
      _materialInputs.add(
        _MaterialEditController(
          name: '',
          percent: 0,
        ),
      );
      _scannedMaterials = _collectEditedMaterials();
    });
  }

  void _removeMaterialInput(int index) {
    final removed = _materialInputs.removeAt(index);
    removed.dispose();

    setState(() {
      _scannedMaterials = _collectEditedMaterials();
    });
  }

  void _syncMaterialInputs() {
    setState(() {
      _scannedMaterials = _collectEditedMaterials();
    });
  }

  Map<String, double> _collectEditedMaterials() {
    final updated = <String, double>{};

    for (final item in _materialInputs) {
      final name = item.nameController.text.trim();
      final percentText = item.percentController.text.trim().replaceAll('%', '');

      if (name.isEmpty) continue;

      final parsed = double.tryParse(percentText) ?? 0.0;
      updated[name] = (updated[name] ?? 0) + parsed;
    }

    return updated;
  }

  double _calculateMaterialsTotal(Map<String, double> materials) {
    return materials.values.fold(0.0, (sum, value) => sum + value);
  }

  bool _isMaterialsTotalValid(Map<String, double> materials) {
    final total = _calculateMaterialsTotal(materials);
    return total >= 99.5 && total <= 100.5;
  }

  double _findMaterialEmissionFactor(String material) {
    final m = material.toLowerCase();

    if (m.contains('organic cotton')) return 5.0;
    if (m.contains('cotton')) return 8.0;
    if (m.contains('linen')) return 6.0;
    if (m.contains('recycled polyester')) return 7.0;
    if (m.contains('polyester')) return 12.0;
    if (m.contains('nylon')) return 14.0;
    if (m.contains('wool')) return 25.0;
    if (m.contains('silk')) return 20.0;
    if (m.contains('viscose') || m.contains('rayon')) return 10.0;
    if (m.contains('polyurethane') || m.contains('spandex')) return 15.0;

    return 10.0;
  }

  double _estimateCarbonFootprint(
      Map<String, double> materials,
      _ClothingTypeOption clothingType,
      ) {
    final weightKg = clothingType.estimatedWeightGram / 1000;

    if (materials.isEmpty) {
      return double.parse((weightKg * 10.0).toStringAsFixed(1));
    }

    double totalPercent =
    materials.values.fold(0.0, (sum, value) => sum + value);

    if (totalPercent <= 0) totalPercent = 100.0;

    double emission = 0.0;

    materials.forEach((material, percent) {
      final factor = _findMaterialEmissionFactor(material);
      emission += (percent / totalPercent) * weightKg * factor;
    });

    if (emission < 0.1) {
      emission = 0.1;
    }

    return double.parse(emission.toStringAsFixed(1));
  }

  int _estimateInitialHealth(Map<String, double> materials) {
    if (materials.isEmpty) return 80;

    double score = 80.0;
    final keys = materials.keys.map((e) => e.toLowerCase()).toList();

    if (materials.length == 1) score += 8;
    if (materials.length >= 3) score -= 8;

    if (keys.any((e) => e.contains('cotton') || e.contains('linen'))) {
      score += 5;
    }

    if (keys.any((e) => e.contains('silk') || e.contains('wool'))) {
      score -= 5;
    }

    if (keys.any((e) => e.contains('polyurethane') || e.contains('spandex'))) {
      score -= 3;
    }

    final clamped = score.round().clamp(60, 95);
    return clamped.toInt();
  }

  String? _validateTitle(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '의류 이름을 입력해 주세요';
    }

    if (text.length < 2) {
      return '의류 이름은 2자 이상 입력해 주세요';
    }

    return null;
  }

  String? _validateMaterialName(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '소재명을 입력해 주세요';
    }

    return null;
  }

  String? _validateMaterialValue(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '필수';
    }

    final parsed = double.tryParse(text.replaceAll('%', ''));

    if (parsed == null) {
      return '숫자만';
    }

    if (parsed < 0 || parsed > 100) {
      return '0~100';
    }

    return null;
  }

  Future<void> _submitClothes() async {
    setState(() {
      _hasTriedSubmit = true;
    });

    final isFormValid = _formKey.currentState?.validate() ?? false;

    if (!isFormValid) return;

    final editedMaterials = _collectEditedMaterials();

    if (editedMaterials.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('소재를 1개 이상 추가해 주세요.'),
        ),
      );
      return;
    }

    final total = _calculateMaterialsTotal(editedMaterials);

    if (!_isMaterialsTotalValid(editedMaterials)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '소재 비율 합계가 100%가 되도록 맞춰 주세요. (현재 ${total.toStringAsFixed(1)}%)',
          ),
        ),
      );
      return;
    }

    final title = _titleController.text.trim();
    final estimatedHealth = _estimateInitialHealth(editedMaterials);
    final estimatedCarbon = _estimateCarbonFootprint(
      editedMaterials,
      _selectedClothingType,
    );

    final newClothes = Clothes(
      title: title,
      category: _selectedCategory,
      health: estimatedHealth,
      materials: editedMaterials,
      careInstruction: _scannedCare,
      carbonFootprint: estimatedCarbon,
    );

    await Provider.of<ClosetProvider>(
      context,
      listen: false,
    ).addClothes(newClothes);

    if (!mounted) return;

    Navigator.pushReplacementNamed(
      context,
      '/report',
      arguments: newClothes,
    );
  }

  void _resetScan() {
    _disposeMaterialInputs();

    setState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _isManualMaterialMode = false;
      _scannedMaterials = {};
      _scannedCare = '';
      _selectedClothingType = _clothingTypeOptions.first;
      _selectedCategory = _selectedClothingType.category;
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
    });

    if (_cameraController == null ||
        !(_cameraController?.value.isInitialized ?? false)) {
      _initializeCamera();
    }
  }

  @override
  Widget build(BuildContext context) {
    return _isScanComplete ? _buildResultView() : _buildCameraView();
  }

  Widget _buildCameraPreviewContent() {
    if (_isScanning && _selectedImage != null) {
      return Image.file(
        _selectedImage!,
        width: 250,
        height: 250,
        fit: BoxFit.cover,
      );
    }

    if (_isCameraInitializing) {
      return const Center(
        child: CircularProgressIndicator(color: Colors.greenAccent),
      );
    }

    if (_cameraErrorMessage != null) {
      return Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.no_photography_outlined,
              color: Colors.white70,
              size: 34,
            ),
            const SizedBox(height: 12),
            Text(
              _cameraErrorMessage!,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 13,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 12),
            TextButton(
              onPressed: _initializeCamera,
              child: const Text('다시 시도'),
            ),
          ],
        ),
      );
    }

    final controller = _cameraController;

    if (controller == null || !controller.value.isInitialized) {
      return const Center(
        child: Text(
          '카메라 준비 중...',
          style: TextStyle(color: Colors.white70, fontSize: 13),
        ),
      );
    }

    final previewSize = controller.value.previewSize;

    if (previewSize == null) {
      return CameraPreview(controller);
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox(
        width: 250,
        height: 250,
        child: FittedBox(
          fit: BoxFit.cover,
          child: SizedBox(
            width: previewSize.height,
            height: previewSize.width,
            child: CameraPreview(controller),
          ),
        ),
      ),
    );
  }

  Widget _buildCameraView() {
    return Container(
      color: Colors.black87,
      width: double.infinity,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text(
            '옷의 케어 라벨을 프레임 안에 맞춰 촬영해 주세요',
            style: TextStyle(color: Colors.white, fontSize: 16),
          ),
          const SizedBox(height: 30),
          Container(
            width: 250,
            height: 250,
            decoration: BoxDecoration(
              border: Border.all(
                color: _isScanning ? Colors.greenAccent : Colors.white,
                width: 2,
              ),
              borderRadius: BorderRadius.circular(12),
              color: Colors.white.withValues(alpha: 0.10),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                Positioned.fill(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: _buildCameraPreviewContent(),
                  ),
                ),
                if (_isScanning)
                  Positioned.fill(
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.60),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            CircularProgressIndicator(
                              color: Colors.greenAccent,
                            ),
                            SizedBox(height: 16),
                            Text(
                              'AI 라벨 분석 중...',
                              style: TextStyle(
                                color: Colors.greenAccent,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 46),
          SizedBox(
            width: double.infinity,
            height: 150,
            child: Stack(
              alignment: Alignment.center,
              children: [
                Positioned(
                  left: 26,
                  bottom: 0,
                  child: GestureDetector(
                    behavior: HitTestBehavior.translucent,
                    onTap: _isScanning ? null : _pickFromGallery,
                    child: SizedBox(
                      width: 74,
                      height: 74,
                      child: Align(
                        alignment: Alignment.bottomCenter,
                        child: Container(
                          width: 54,
                          height: 54,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.14),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: Colors.white.withValues(alpha: 0.45),
                            ),
                          ),
                          child: const Icon(
                            Icons.photo_library_outlined,
                            color: Colors.white,
                            size: 25,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
                Positioned(
                  top: 15,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: GestureDetector(
                      behavior: HitTestBehavior.translucent,
                      onTap: _isScanning ? null : _takePicture,
                      child: Container(
                        width: 74,
                        height: 74,
                        decoration: BoxDecoration(
                          color: _isScanning
                              ? Colors.grey
                              : const Color(0xFF4A4EFE),
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white, width: 4),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF4A4EFE)
                                  .withValues(alpha: 0.35),
                              blurRadius: 18,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: const Icon(
                          Icons.camera_alt,
                          color: Colors.white,
                          size: 30,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildResultView() {
    final editedMaterials = _collectEditedMaterials();
    final previewHealth = _estimateInitialHealth(editedMaterials);
    final previewCarbon = _estimateCarbonFootprint(
      editedMaterials,
      _selectedClothingType,
    );
    final totalMaterials = _calculateMaterialsTotal(editedMaterials);
    final isTotalValid =
        editedMaterials.isNotEmpty && _isMaterialsTotalValid(editedMaterials);

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor =
    isDark ? const Color(0xFF121212) : const Color(0xFFF8F9FC);
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor =
    isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark ? const Color(0xFFD1D1D6) : Colors.grey;
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;
    final previewBoxColor =
    isDark ? const Color(0xFF1F2A3D) : Colors.green.shade50;
    final previewBorderColor =
    isDark ? const Color(0xFF2C4C7A) : Colors.green.shade100;
    final careBoxColor = isDark ? const Color(0xFF1E2A3A) : Colors.blue.shade50;

    return Container(
      color: backgroundColor,
      child: Form(
        key: _formKey,
        autovalidateMode: _hasTriedSubmit
            ? AutovalidateMode.always
            : AutovalidateMode.disabled,
        child: SingleChildScrollView(
          keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 140),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Center(
                child: Icon(Icons.check_circle, color: Colors.green, size: 60),
              ),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  '스캔 완료!',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: primaryText,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  _isManualMaterialMode
                      ? '인식되지 않은 정보는 직접 입력해 주세요.'
                      : '의류 무게 기준과 분석 결과를 확인해 주세요.',
                  style: TextStyle(fontSize: 14, color: secondaryText),
                  textAlign: TextAlign.center,
                ),
              ),
              const SizedBox(height: 32),
              Text(
                '기본 정보 수정',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: borderColor),
                ),
                child: Column(
                  children: [
                    TextFormField(
                      controller: _titleController,
                      validator: _validateTitle,
                      style: TextStyle(color: primaryText),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: inputFillColor,
                        labelText: '의류 이름',
                        labelStyle: TextStyle(color: secondaryText),
                        hintText: '예: 홍길동 코튼 맨투맨',
                        hintStyle: TextStyle(color: secondaryText),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                        prefixIcon: const Icon(Icons.checkroom_outlined),
                      ),
                    ),
                    const SizedBox(height: 16),
                    InkWell(
                      onTap: () async {
                        final picked = await _showClothingTypePicker(
                          initialSelection: _selectedClothingType,
                        );

                        if (!mounted || picked == null) return;
                        _applyClothingType(picked);
                      },
                      borderRadius: BorderRadius.circular(10),
                      child: InputDecorator(
                        decoration: InputDecoration(
                          filled: true,
                          fillColor: inputFillColor,
                          labelText: '무게 기준',
                          labelStyle: TextStyle(color: secondaryText),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                          prefixIcon: const Icon(Icons.scale_outlined),
                          suffixIcon: Icon(
                            Icons.keyboard_arrow_down,
                            color: secondaryText,
                          ),
                        ),
                        child: Text(
                          '${_selectedClothingType.label} · ${_selectedClothingType.weightDisplayText}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: primaryText,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: previewBoxColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: previewBorderColor),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.analytics_outlined, color: Colors.green),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        '무게 기준: ${_selectedClothingType.label} · ${_selectedClothingType.weightDisplayText}\n'
                            '예상 건강도: $previewHealth%\n'
                            '예상 탄소발자국: ${previewCarbon.toStringAsFixed(1)} kg CO2eq',
                        softWrap: true,
                        style: TextStyle(
                          fontSize: 14,
                          color: primaryText,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (_isManualMaterialMode) ...[
                const SizedBox(height: 16),
                _buildManualNotice(
                  primaryText: primaryText,
                  secondaryText: secondaryText,
                  borderColor: borderColor,
                  cardColor: cardColor,
                ),
              ],
              const SizedBox(height: 24),
              Text(
                '소재 및 혼용률',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _materialInputs.isEmpty
                    ? '소재를 직접 추가해 주세요.'
                    : '현재 소재 합계: ${totalMaterials.toStringAsFixed(1)}%',
                style: TextStyle(
                  color: _materialInputs.isEmpty
                      ? secondaryText
                      : isTotalValid
                      ? Colors.green
                      : Colors.redAccent,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: cardColor,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: borderColor),
                ),
                child: Column(
                  children: [
                    if (_materialInputs.isEmpty)
                      _buildEmptyMaterialEditor(
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                      )
                    else
                      ...List.generate(
                        _materialInputs.length,
                            (index) => Padding(
                          padding: EdgeInsets.only(
                            bottom: index == _materialInputs.length - 1 ? 0 : 12,
                          ),
                          child: _buildMaterialRow(
                            index,
                            primaryText: primaryText,
                            secondaryText: secondaryText,
                            inputFillColor: inputFillColor,
                          ),
                        ),
                      ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _addMaterialInput,
                        icon: const Icon(Icons.add),
                        label: const Text('소재 추가'),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: careBoxColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.local_laundry_service, color: Colors.blue),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'AI 분석 세탁 지침\n$_scannedCare',
                        softWrap: true,
                        style: TextStyle(
                          fontSize: 14,
                          color: primaryText,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 40),
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton(
                  onPressed: _submitClothes,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF4A4EFE),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: const Text(
                    '옷장에 저장하기',
                    style: TextStyle(
                      fontSize: 16,
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Center(
                child: TextButton(
                  onPressed: _resetScan,
                  child: Text(
                    '다시 촬영',
                    style: TextStyle(color: secondaryText),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildManualNotice({
    required Color primaryText,
    required Color secondaryText,
    required Color borderColor,
    required Color cardColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.edit_note, color: Color(0xFF4A4EFE)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'AI가 소재 정보를 정확히 읽지 못했어요. 라벨에 적힌 소재명과 혼용률을 직접 추가해 주세요.',
              softWrap: true,
              style: TextStyle(
                color: secondaryText,
                fontSize: 13,
                height: 1.5,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyMaterialEditor({
    required Color primaryText,
    required Color secondaryText,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: secondaryText.withValues(alpha: 0.25)),
      ),
      child: Text(
        '인식된 소재가 없어요. 아래 버튼으로 소재와 혼용률을 직접 추가해 주세요.',
        textAlign: TextAlign.center,
        style: TextStyle(
          color: secondaryText,
          fontSize: 13,
          height: 1.5,
        ),
      ),
    );
  }

  Widget _buildMaterialRow(
      int index, {
        required Color primaryText,
        required Color secondaryText,
        required Color inputFillColor,
      }) {
    final item = _materialInputs[index];

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextFormField(
            controller: item.nameController,
            validator: _validateMaterialName,
            style: TextStyle(
              color: primaryText,
              fontSize: 14,
            ),
            decoration: InputDecoration(
              filled: true,
              fillColor: inputFillColor,
              labelText: '소재명',
              hintText: '예: cotton',
              labelStyle: TextStyle(color: secondaryText),
              hintStyle: TextStyle(color: secondaryText),
              isDense: true,
              contentPadding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            onChanged: (_) => _syncMaterialInputs(),
          ),
        ),
        const SizedBox(width: 8),
        SizedBox(
          width: 86,
          child: TextFormField(
            controller: item.percentController,
            validator: _validateMaterialValue,
            style: TextStyle(
              color: primaryText,
              fontSize: 14,
            ),
            textAlign: TextAlign.right,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              filled: true,
              fillColor: inputFillColor,
              suffixText: '%',
              suffixStyle: TextStyle(color: secondaryText),
              isDense: true,
              contentPadding: const EdgeInsets.fromLTRB(8, 12, 8, 10),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            onChanged: (_) => _syncMaterialInputs(),
          ),
        ),
        const SizedBox(width: 4),
        SizedBox(
          width: 36,
          child: IconButton(
            onPressed: () => _removeMaterialInput(index),
            icon: Icon(
              Icons.close,
              color: secondaryText,
              size: 20,
            ),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(
              minWidth: 36,
              minHeight: 48,
            ),
          ),
        ),
      ],
    );
  }
}

class _ClothingTypePickerSheet extends StatefulWidget {
  const _ClothingTypePickerSheet({
    required this.options,
    required this.initialSelection,
    required this.onSelected,
  });

  final List<_ClothingTypeOption> options;
  final _ClothingTypeOption initialSelection;
  final ValueChanged<_ClothingTypeOption> onSelected;

  @override
  State<_ClothingTypePickerSheet> createState() =>
      _ClothingTypePickerSheetState();
}

class _ClothingTypePickerSheetState extends State<_ClothingTypePickerSheet> {
  final TextEditingController _directNameController = TextEditingController();
  final TextEditingController _directWeightController = TextEditingController();

  bool _isDirectInputMode = false;
  String _directCategory = '상의';
  String? _directErrorText;

  @override
  void initState() {
    super.initState();

    _directCategory =
    widget.initialSelection.category == '하의' ? '하의' : '상의';

    if (widget.initialSelection.isDirectWeight) {
      _directNameController.text = widget.initialSelection.label;
      _directWeightController.text = _ClothingTypeOption._formatWeightGram(
        widget.initialSelection.estimatedWeightGram,
      );
    }
  }

  @override
  void dispose() {
    _directNameController.dispose();
    _directWeightController.dispose();
    super.dispose();
  }

  void _submitDirectInput() {
    final name = _directNameController.text.trim();
    final weightText = _directWeightController.text.trim();
    final weight = double.tryParse(weightText);

    if (name.isEmpty) {
      setState(() {
        _directErrorText = '의류 종류를 입력해 주세요.';
      });
      return;
    }

    if (weight == null || weight <= 0) {
      setState(() {
        _directErrorText = '실제 무게를 g 단위로 입력해 주세요.';
      });
      return;
    }

    widget.onSelected(
      _ClothingTypeOption.directWeight(
        label: name,
        category: _directCategory,
        weightGram: weight,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final sheetColor = isDark ? const Color(0xFF121212) : Colors.white;

    return SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: DraggableScrollableSheet(
          initialChildSize: 0.78,
          minChildSize: 0.18,
          maxChildSize: 0.78,
          expand: false,
          shouldCloseOnMinExtent: true,
          builder: (context, scrollController) {
            return Container(
              decoration: BoxDecoration(
                color: sheetColor,
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(24),
                ),
              ),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 180),
                switchInCurve: Curves.easeOut,
                switchOutCurve: Curves.easeOut,
                child: _isDirectInputMode
                    ? _buildDirectInputView(context, scrollController)
                    : _buildOptionListView(context, scrollController),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildDragHandle(bool isDark) {
    return Center(
      child: Container(
        width: 38,
        height: 4,
        decoration: BoxDecoration(
          color: isDark ? Colors.white24 : Colors.black12,
          borderRadius: BorderRadius.circular(999),
        ),
      ),
    );
  }

  Widget _buildOptionListView(
      BuildContext context,
      ScrollController scrollController,
      ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor =
    isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText =
    isDark ? const Color(0xFFD1D1D6) : const Color(0xFF777777);

    return ListView(
      key: const ValueKey('option-list'),
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
      children: [
        _buildDragHandle(isDark),
        const SizedBox(height: 18),
        Text(
          '의류 종류 선택',
          style: TextStyle(
            color: primaryText,
            fontSize: 22,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '탄소발자국 계산에 사용할 의류 무게 범위를 선택해 주세요.',
          style: TextStyle(
            color: secondaryText,
            fontSize: 13,
            height: 1.5,
          ),
        ),
        const SizedBox(height: 18),
        ...widget.options.map((option) {
          final isSelected = option.isDirectWeightPlaceholder
              ? widget.initialSelection.isDirectWeight ||
              widget.initialSelection.isDirectWeightPlaceholder
              : option.label == widget.initialSelection.label;

          return Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: InkWell(
              onTap: () {
                if (option.isDirectWeightPlaceholder) {
                  setState(() {
                    _isDirectInputMode = true;
                    _directErrorText = null;
                  });
                  return;
                }

                widget.onSelected(option);
              },
              borderRadius: BorderRadius.circular(14),
              child: Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: isSelected
                      ? const Color(0xFF4A4EFE).withValues(
                    alpha: isDark ? 0.20 : 0.10,
                  )
                      : cardColor,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color:
                    isSelected ? const Color(0xFF4A4EFE) : borderColor,
                    width: isSelected ? 1.5 : 1,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 42,
                      height: 42,
                      decoration: BoxDecoration(
                        color: isSelected
                            ? const Color(0xFF4A4EFE)
                            : (isDark
                            ? const Color(0xFF2A2A2E)
                            : const Color(0xFFF2F3F8)),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Icon(
                        option.icon,
                        color: isSelected
                            ? Colors.white
                            : const Color(0xFF4A4EFE),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            option.label,
                            style: TextStyle(
                              color: primaryText,
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            option.isDirectWeightPlaceholder
                                ? '실제 무게를 알고 있어요'
                                : '${option.category} · 예상 무게 ${option.weightRangeLabel}',
                            style: TextStyle(
                              color: secondaryText,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isSelected)
                      const Icon(
                        Icons.check_circle,
                        color: Color(0xFF4A4EFE),
                      )
                    else
                      Icon(
                        option.isDirectWeightPlaceholder
                            ? Icons.scale_outlined
                            : Icons.chevron_right,
                        color: secondaryText,
                      ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildDirectInputView(
      BuildContext context,
      ScrollController scrollController,
      ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor =
    isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText =
    isDark ? const Color(0xFFD1D1D6) : const Color(0xFF777777);
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;

    return ListView(
      key: const ValueKey('direct-input'),
      controller: scrollController,
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
      children: [
        _buildDragHandle(isDark),
        const SizedBox(height: 10),
        Row(
          children: [
            IconButton(
              onPressed: () {
                setState(() {
                  _isDirectInputMode = false;
                  _directErrorText = null;
                });
              },
              icon: Icon(
                Icons.arrow_back_ios_new_rounded,
                color: primaryText,
                size: 20,
              ),
            ),
            Expanded(
              child: Text(
                '직접 무게 입력',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: primaryText,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(width: 48),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          '실제 무게를 알고 있다면 더 정확하게 탄소발자국을 계산할 수 있어요.',
          style: TextStyle(
            color: secondaryText,
            fontSize: 13,
            height: 1.5,
          ),
        ),
        const SizedBox(height: 18),
        TextField(
          controller: _directNameController,
          autofocus: true,
          style: TextStyle(color: primaryText),
          textInputAction: TextInputAction.next,
          decoration: InputDecoration(
            filled: true,
            fillColor: inputFillColor,
            labelText: '의류 종류',
            hintText: '예: 가디건, 조끼, 트레이닝복',
            labelStyle: TextStyle(color: secondaryText),
            hintStyle: TextStyle(color: secondaryText),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            prefixIcon: const Icon(Icons.edit_outlined),
          ),
          onChanged: (_) {
            if (_directErrorText == null) return;
            setState(() {
              _directErrorText = null;
            });
          },
        ),
        const SizedBox(height: 14),
        TextField(
          controller: _directWeightController,
          style: TextStyle(color: primaryText),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textInputAction: TextInputAction.done,
          decoration: InputDecoration(
            filled: true,
            fillColor: inputFillColor,
            labelText: '실제 무게',
            hintText: '예: 620',
            suffixText: 'g',
            labelStyle: TextStyle(color: secondaryText),
            hintStyle: TextStyle(color: secondaryText),
            suffixStyle: TextStyle(color: secondaryText),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            prefixIcon: const Icon(Icons.scale_outlined),
          ),
          onChanged: (_) {
            if (_directErrorText == null) return;
            setState(() {
              _directErrorText = null;
            });
          },
          onSubmitted: (_) => _submitDirectInput(),
        ),
        const SizedBox(height: 16),
        Text(
          '분류',
          style: TextStyle(
            color: primaryText,
            fontSize: 14,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _CategoryChoiceChip(
                label: '상의',
                selected: _directCategory == '상의',
                onTap: () {
                  setState(() {
                    _directCategory = '상의';
                  });
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _CategoryChoiceChip(
                label: '하의',
                selected: _directCategory == '하의',
                onTap: () {
                  setState(() {
                    _directCategory = '하의';
                  });
                },
              ),
            ),
          ],
        ),
        if (_directErrorText != null) ...[
          const SizedBox(height: 12),
          Text(
            _directErrorText!,
            style: const TextStyle(
              color: Colors.redAccent,
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
        const SizedBox(height: 20),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: cardColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: borderColor),
          ),
          child: Text(
            '무게는 의류 한 벌 기준으로 g 단위로 입력해 주세요.',
            style: TextStyle(
              color: secondaryText,
              fontSize: 13,
              height: 1.5,
            ),
          ),
        ),
        const SizedBox(height: 20),
        SizedBox(
          width: double.infinity,
          height: 50,
          child: ElevatedButton(
            onPressed: _submitDirectInput,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF4A4EFE),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
            child: const Text(
              '적용하기',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _CategoryChoiceChip extends StatelessWidget {
  const _CategoryChoiceChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final borderColor =
    selected ? const Color(0xFF4A4EFE) : const Color(0xFF8C8C8C);
    final backgroundColor = selected
        ? const Color(0xFF4A4EFE).withValues(alpha: isDark ? 0.22 : 0.10)
        : Colors.transparent;
    final textColor = selected
        ? const Color(0xFF4A4EFE)
        : (isDark ? Colors.white : Colors.black87);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        height: 46,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: textColor,
            fontSize: 14,
            fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

class _MaterialEditController {
  _MaterialEditController({
    required String name,
    required double percent,
  })  : nameController = TextEditingController(text: name),
        percentController = TextEditingController(
          text: _formatPercent(percent),
        );

  final TextEditingController nameController;
  final TextEditingController percentController;

  void dispose() {
    nameController.dispose();
    percentController.dispose();
  }

  static String _formatPercent(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}

class _ClothingTypeOption {
  const _ClothingTypeOption({
    required this.label,
    required this.category,
    required this.weightRangeLabel,
    required this.estimatedWeightGram,
    required this.icon,
    this.isDirectWeightPlaceholder = false,
    this.isDirectWeight = false,
  });

  factory _ClothingTypeOption.directWeight({
    required String label,
    required String category,
    required double weightGram,
  }) {
    return _ClothingTypeOption(
      label: label,
      category: category,
      weightRangeLabel: '${_formatWeightGram(weightGram)}g',
      estimatedWeightGram: weightGram,
      icon: Icons.scale_outlined,
      isDirectWeight: true,
    );
  }

  final String label;
  final String category;
  final String weightRangeLabel;
  final double estimatedWeightGram;
  final IconData icon;
  final bool isDirectWeightPlaceholder;
  final bool isDirectWeight;

  String get defaultTitle {
    if (isDirectWeightPlaceholder) return '홍길동 기타 의류';
    return '홍길동 $label';
  }

  String get weightDisplayText {
    if (isDirectWeight) {
      return '실제 무게 ${_formatWeightGram(estimatedWeightGram)}g';
    }

    if (isDirectWeightPlaceholder) {
      return '실제 무게 입력';
    }

    return '예상 무게 $weightRangeLabel';
  }

  static String _formatWeightGram(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}