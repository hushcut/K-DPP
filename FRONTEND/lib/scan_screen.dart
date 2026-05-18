import 'dart:io';

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

  File? _selectedImage;
  final ImagePicker _picker = ImagePicker();
  final ScanApiService _scanApiService = const ScanApiService();

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  Map<String, double> _scannedMaterials = {};
  String _scannedCare = '';

  final Map<String, TextEditingController> _materialControllers = {};
  final TextEditingController _titleController = TextEditingController();

  _ClothingTypeOption _selectedClothingType = _clothingTypeOptions.first;
  String _selectedCategory = '상의';

  @override
  void initState() {
    super.initState();
    _titleController.text = '새로 스캔한 의류';
  }

  @override
  void dispose() {
    for (final controller in _materialControllers.values) {
      controller.dispose();
    }
    _titleController.dispose();
    super.dispose();
  }

  Future<void> _takePicture() async {
    final XFile? photo = await _picker.pickImage(source: ImageSource.camera);

    if (photo == null) return;

    setState(() {
      _selectedImage = File(photo.path);
      _isScanning = true;
      _isScanComplete = false;
      _hasTriedSubmit = false;
    });

    try {
      final ScanResult result =
      await _scanApiService.scanLabel(imageFile: _selectedImage!);

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
      ) ??
          inferredType;

      if (!mounted) return;

      _setMaterialControllers(result.materials);

      setState(() {
        _selectedClothingType = selectedType;
        _selectedCategory = selectedType.category;
        _isScanComplete = true;
        _scannedMaterials = result.materials;
        _scannedCare = result.careInstruction;
        _titleController.text = (result.title?.trim().isNotEmpty ?? false)
            ? result.title!.trim()
            : selectedType.defaultTitle;
      });
    } on ScanApiException catch (e) {
      _showErrorFallback(e.message);
    } catch (e) {
      debugPrint('서버 통신 실패: $e');
      _showErrorFallback('서버 연결이 불안정해 임시 결과를 표시합니다.');
    }
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
      enableDrag: canDismiss,
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

  void _setMaterialControllers(Map<String, double> materials) {
    for (final controller in _materialControllers.values) {
      controller.dispose();
    }
    _materialControllers.clear();

    materials.forEach((key, value) {
      _materialControllers[key] = TextEditingController(
        text:
        value % 1 == 0 ? value.toInt().toString() : value.toStringAsFixed(1),
      );
    });
  }

  Map<String, double> _collectEditedMaterials() {
    final updated = <String, double>{};

    _materialControllers.forEach((key, controller) {
      final parsed = double.tryParse(controller.text.trim()) ?? 0.0;
      updated[key] = parsed;
    });

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

    if (m.contains('cotton') || m.contains('면') || m.contains('코튼')) {
      return 8.3;
    }
    if (m.contains('polyester') ||
        m.contains('폴리에스터') ||
        m.contains('poly')) {
      return 9.5;
    }
    if (m.contains('nylon') || m.contains('나일론')) return 11.0;
    if (m.contains('wool') || m.contains('울') || m.contains('모')) return 13.9;
    if (m.contains('linen') || m.contains('린넨') || m.contains('리넨')) {
      return 4.5;
    }

    return 10.0;
  }

  double _estimateMixedEmissionFactor(Map<String, double> materials) {
    if (materials.isEmpty) return 10.0;

    double totalPercent =
    materials.values.fold(0.0, (sum, value) => sum + value);
    if (totalPercent <= 0) totalPercent = 100.0;

    double mixedFactor = 0.0;

    materials.forEach((material, percent) {
      final factor = _findMaterialEmissionFactor(material);
      mixedFactor += (percent / totalPercent) * factor;
    });

    return mixedFactor;
  }

  _CarbonFootprintRange _estimateCarbonFootprintRange(
      Map<String, double> materials,
      _ClothingTypeOption clothingType,
      ) {
    final mixedFactor = _estimateMixedEmissionFactor(materials);
    final minEmission = mixedFactor * (clothingType.minWeightGram / 1000);
    final maxEmission = mixedFactor * (clothingType.maxWeightGram / 1000);

    return _CarbonFootprintRange(
      min: minEmission < 0.1 ? 0.1 : minEmission,
      max: maxEmission < 0.1 ? 0.1 : maxEmission,
    );
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

  String? _validateMaterialValue(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '필수';
    }

    final parsed = double.tryParse(text);
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
    final estimatedCarbonRange = _estimateCarbonFootprintRange(
      editedMaterials,
      _selectedClothingType,
    );

    final newClothes = Clothes(
      title: title,
      category: _selectedCategory,
      health: estimatedHealth,
      materials: editedMaterials,
      careInstruction: _scannedCare,
      carbonFootprint: estimatedCarbonRange.midpoint,
      carbonFootprintMin: estimatedCarbonRange.min,
      carbonFootprintMax: estimatedCarbonRange.max,
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

  void _showErrorFallback([
    String message = '서버 연결이 불안정해 임시 결과를 표시합니다.',
  ]) {
    Future.delayed(const Duration(seconds: 1), () async {
      if (!mounted) return;

      final fallbackMaterials = <String, double>{
        'cotton': 80,
        'polyester': 20,
      };

      setState(() {
        _isScanning = false;
      });

      final selectedType = await _showClothingTypePicker(
        initialSelection: _selectedClothingType,
        canDismiss: false,
      ) ??
          _selectedClothingType;

      if (!mounted) return;

      _setMaterialControllers(fallbackMaterials);

      setState(() {
        _selectedClothingType = selectedType;
        _selectedCategory = selectedType.category;
        _isScanComplete = true;
        _scannedMaterials = fallbackMaterials;
        _scannedCare = '30도 이하 물에서 중성세제로 손세탁하세요.';
        _titleController.text = selectedType.defaultTitle;
        _hasTriedSubmit = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    });
  }

  void _resetScan() {
    for (final controller in _materialControllers.values) {
      controller.dispose();
    }
    _materialControllers.clear();

    setState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _scannedMaterials = {};
      _scannedCare = '';
      _selectedClothingType = _clothingTypeOptions.first;
      _selectedCategory = _selectedClothingType.category;
      _titleController.text = '새로 스캔한 의류';
      _hasTriedSubmit = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return _isScanComplete ? _buildResultView() : _buildCameraView();
  }

  Widget _buildCameraView() {
    return Container(
      color: Colors.black87,
      width: double.infinity,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text(
            '옷의 케어 라벨을 촬영해 주세요',
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
                if (_selectedImage != null)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: Image.file(
                      _selectedImage!,
                      width: 250,
                      height: 250,
                      fit: BoxFit.cover,
                    ),
                  ),
                if (_isScanning)
                  Container(
                    color: Colors.black.withValues(alpha: 0.60),
                    child: const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          CircularProgressIndicator(color: Colors.greenAccent),
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
              ],
            ),
          ),
          const SizedBox(height: 50),
          GestureDetector(
            onTap: _isScanning ? null : _takePicture,
            child: Container(
              width: 70,
              height: 70,
              decoration: BoxDecoration(
                color: _isScanning ? Colors.grey : const Color(0xFF4A4EFE),
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white, width: 4),
              ),
              child: const Icon(Icons.camera_alt, color: Colors.white, size: 30),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildResultView() {
    final previewHealth = _estimateInitialHealth(_scannedMaterials);
    final previewCarbonRange = _estimateCarbonFootprintRange(
      _scannedMaterials,
      _selectedClothingType,
    );
    final totalMaterials = _calculateMaterialsTotal(_collectEditedMaterials());
    final isTotalValid = _isMaterialsTotalValid(_collectEditedMaterials());

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
                  '의류 무게 기준과 분석 결과를 확인해 주세요.',
                  style: TextStyle(fontSize: 14, color: secondaryText),
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
                  children: [
                    const Icon(Icons.analytics_outlined, color: Colors.green),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        '무게 기준: ${_selectedClothingType.label} · ${_selectedClothingType.weightDisplayText}\n'
                            '예상 건강도: $previewHealth%\n'
                            '예상 탄소발자국: ${previewCarbonRange.displayText}',
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
              const SizedBox(height: 24),
              Text(
                'AI 인식 소재 결과',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: primaryText,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '현재 소재 합계: ${totalMaterials.toStringAsFixed(1)}%',
                style: TextStyle(
                  color: isTotalValid ? Colors.green : Colors.redAccent,
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
                  children: _scannedMaterials.entries.map((entry) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12.0),
                      child: _buildMaterialRow(
                        entry.key,
                        entry.key.toUpperCase(),
                        primaryText: primaryText,
                        secondaryText: secondaryText,
                        inputFillColor: inputFillColor,
                      ),
                    );
                  }).toList(),
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
                  children: [
                    const Icon(Icons.local_laundry_service, color: Colors.blue),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'AI 분석 세탁 지침\n$_scannedCare',
                        style: TextStyle(fontSize: 14, color: primaryText),
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

  Widget _buildMaterialRow(
      String key,
      String displayName, {
        required Color primaryText,
        required Color secondaryText,
        required Color inputFillColor,
      }) {
    final controller = _materialControllers[key]!;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 14),
            child: Text(
              displayName,
              style: TextStyle(fontSize: 16, color: primaryText),
            ),
          ),
        ),
        SizedBox(
          width: 100,
          child: TextFormField(
            controller: controller,
            validator: _validateMaterialValue,
            style: TextStyle(color: primaryText),
            textAlign: TextAlign.right,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              filled: true,
              fillColor: inputFillColor,
              suffixText: '%',
              suffixStyle: TextStyle(color: secondaryText),
              isDense: true,
              contentPadding: const EdgeInsets.only(
                bottom: 4,
                right: 8,
                top: 12,
              ),
            ),
            onChanged: (_) {
              setState(() {
                _scannedMaterials[key] =
                    double.tryParse(controller.text.trim()) ?? 0.0;
              });
            },
          ),
        ),
      ],
    );
  }
}


class _CarbonFootprintRange {
  const _CarbonFootprintRange({
    required this.min,
    required this.max,
  });

  final double min;
  final double max;

  double get midpoint => (min + max) / 2;

  String get displayText {
    if ((min - max).abs() < 0.05) {
      return '${midpoint.toStringAsFixed(1)} kg CO2eq';
    }

    return '${min.toStringAsFixed(1)}~${max.toStringAsFixed(1)} kg CO2eq';
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
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height * 0.82,
          ),
          child: Container(
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
                  ? _buildDirectInputView(context)
                  : _buildOptionListView(context),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildOptionListView(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor =
    isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade200;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText =
    isDark ? const Color(0xFFD1D1D6) : const Color(0xFF777777);

    return Padding(
      key: const ValueKey('option-list'),
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 38,
              height: 4,
              decoration: BoxDecoration(
                color: isDark ? Colors.white24 : Colors.black12,
                borderRadius: BorderRadius.circular(999),
              ),
            ),
          ),
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
          Flexible(
            child: ListView.separated(
              shrinkWrap: true,
              itemCount: widget.options.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final option = widget.options[index];
                final isSelected = option.isDirectWeightPlaceholder
                    ? widget.initialSelection.isDirectWeight ||
                    widget.initialSelection.isDirectWeightPlaceholder
                    : option.label == widget.initialSelection.label;

                return InkWell(
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
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDirectInputView(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor =
    isDark ? const Color(0xFF2C2C2E) : Colors.grey.shade300;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText =
    isDark ? const Color(0xFFD1D1D6) : const Color(0xFF777777);
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;

    return SingleChildScrollView(
      key: const ValueKey('direct-input'),
      padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 38,
              height: 4,
              decoration: BoxDecoration(
                color: isDark ? Colors.white24 : Colors.black12,
                borderRadius: BorderRadius.circular(999),
              ),
            ),
          ),
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
      ),
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
    final textColor =
    selected ? const Color(0xFF4A4EFE) : (isDark ? Colors.white : Colors.black87);

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

  double get minWeightGram {
    if (isDirectWeight || isDirectWeightPlaceholder) return estimatedWeightGram;

    final match = RegExp(r'(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)').firstMatch(
      weightRangeLabel,
    );

    if (match == null) return estimatedWeightGram;
    return double.tryParse(match.group(1) ?? '') ?? estimatedWeightGram;
  }

  double get maxWeightGram {
    if (isDirectWeight || isDirectWeightPlaceholder) return estimatedWeightGram;

    final match = RegExp(r'(\d+(?:\.\d+)?)\s*~\s*(\d+(?:\.\d+)?)').firstMatch(
      weightRangeLabel,
    );

    if (match == null) return estimatedWeightGram;
    return double.tryParse(match.group(2) ?? '') ?? estimatedWeightGram;
  }

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
