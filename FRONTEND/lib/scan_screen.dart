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

  final List<String> _categoryOptions = ['상의', '하의'];
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

      _setMaterialControllers(result.materials);

      if (!mounted) return;
      setState(() {
        _isScanning = false;
        _isScanComplete = true;
        _scannedMaterials = result.materials;
        _scannedCare = result.careInstruction;
        _titleController.text =
        (result.title?.trim().isNotEmpty ?? false)
            ? result.title!.trim()
            : '새로 스캔한 의류';
        _selectedCategory = _normalizeCategory(result.category);
      });
    } on ScanApiException catch (e) {
      _showErrorFallback(e.message);
    } catch (e) {
      debugPrint('🔌 서버 통신 실패: $e');
      _showErrorFallback('서버 통신 실패로 임시 결과를 표시합니다.');
    }
  }

  String _normalizeCategory(String? category) {
    if (category == null) return '상의';
    if (_categoryOptions.contains(category)) return category;
    return '상의';
  }

  void _setMaterialControllers(Map<String, double> materials) {
    for (final controller in _materialControllers.values) {
      controller.dispose();
    }
    _materialControllers.clear();

    materials.forEach((key, value) {
      _materialControllers[key] = TextEditingController(
        text: value % 1 == 0
            ? value.toInt().toString()
            : value.toStringAsFixed(1),
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
      String category,
      ) {
    if (materials.isEmpty) {
      return category == '하의' ? 12.0 : 9.0;
    }

    double totalPercent =
    materials.values.fold(0.0, (sum, value) => sum + value);
    if (totalPercent <= 0) totalPercent = 100.0;

    double emission = 0.0;

    materials.forEach((material, percent) {
      final factor = _findMaterialEmissionFactor(material);
      emission += (percent / totalPercent) * factor;
    });

    final categoryMultiplier = category == '하의' ? 1.15 : 1.0;
    final result = emission * categoryMultiplier;

    return double.parse(result.toStringAsFixed(1));
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
    final estimatedCarbon = _estimateCarbonFootprint(
      editedMaterials,
      _selectedCategory,
    );

    await Provider.of<ClosetProvider>(
      context,
      listen: false,
    ).addClothes(
      Clothes(
        title: title,
        category: _selectedCategory,
        health: estimatedHealth,
        materials: editedMaterials,
        careInstruction: _scannedCare,
        carbonFootprint: estimatedCarbon,
      ),
    );

    if (!mounted) return;

    Navigator.pushReplacementNamed(
      context,
      '/main',
      arguments: 2,
    );
  }

  void _showErrorFallback([
    String message = '서버 미연결: 임시 결과 화면을 띄웁니다.',
  ]) {
    Future.delayed(const Duration(seconds: 1), () {
      if (!mounted) return;

      final fallbackMaterials = <String, double>{
        'cotton': 80,
        'polyester': 20,
      };

      _setMaterialControllers(fallbackMaterials);

      setState(() {
        _isScanning = false;
        _isScanComplete = true;
        _scannedMaterials = fallbackMaterials;
        _scannedCare = '30도 이하 물에서 중성세제로 손세탁하세요.';
        _titleController.text = '새로 스캔한 의류';
        _selectedCategory = '상의';
        _hasTriedSubmit = false;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('옷장에 저장되었습니다.')),
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
      _titleController.text = '새로 스캔한 의류';
      _selectedCategory = '상의';
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
              color: Colors.white.withOpacity(0.1),
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
                    color: Colors.black.withOpacity(0.6),
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
    final previewCarbon =
    _estimateCarbonFootprint(_scannedMaterials, _selectedCategory);
    final totalMaterials = _calculateMaterialsTotal(_collectEditedMaterials());
    final isTotalValid = _isMaterialsTotalValid(_collectEditedMaterials());

    return Form(
      key: _formKey,
      autovalidateMode: _hasTriedSubmit
          ? AutovalidateMode.always
          : AutovalidateMode.disabled,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Center(
              child: Icon(Icons.check_circle, color: Colors.green, size: 60),
            ),
            const SizedBox(height: 16),
            const Center(
              child: Text(
                '스캔 완료!',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
            ),
            const SizedBox(height: 32),

            const Text(
              '기본 정보 수정',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),

            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.grey.shade300),
              ),
              child: Column(
                children: [
                  TextFormField(
                    controller: _titleController,
                    validator: _validateTitle,
                    decoration: InputDecoration(
                      labelText: '의류 이름',
                      hintText: '예: 오가닉 코튼 맨투맨',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                      prefixIcon: const Icon(Icons.checkroom_outlined),
                    ),
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    value: _selectedCategory,
                    decoration: InputDecoration(
                      labelText: '카테고리',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                      prefixIcon: const Icon(Icons.category_outlined),
                    ),
                    items: _categoryOptions.map((category) {
                      return DropdownMenuItem(
                        value: category,
                        child: Text(category),
                      );
                    }).toList(),
                    onChanged: (value) {
                      if (value == null) return;
                      setState(() {
                        _selectedCategory = value;
                      });
                    },
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.green.shade100),
              ),
              child: Row(
                children: [
                  const Icon(Icons.analytics_outlined, color: Colors.green),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      '예상 건강도: $previewHealth%\n'
                          '예상 탄소발자국: ${previewCarbon.toStringAsFixed(1)} kg CO2eq',
                      style: const TextStyle(fontSize: 14, color: Colors.black87),
                    ),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            const Text(
              'AI 인식 소재 결과',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
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
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.grey.shade300),
              ),
              child: Column(
                children: _scannedMaterials.entries.map((entry) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12.0),
                    child: _buildMaterialRow(entry.key, entry.key.toUpperCase()),
                  );
                }).toList(),
              ),
            ),

            const SizedBox(height: 24),

            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  const Icon(Icons.local_laundry_service, color: Colors.blue),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'AI 분석 세탁 지침:\n$_scannedCare',
                      style: const TextStyle(fontSize: 14, color: Colors.black87),
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
                  '홍길동님의 옷장에 등록하기',
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
                child: const Text(
                  '다시 촬영하기',
                  style: TextStyle(color: Colors.grey),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMaterialRow(String key, String displayName) {
    final controller = _materialControllers[key]!;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 14),
            child: Text(
              displayName,
              style: const TextStyle(fontSize: 16),
            ),
          ),
        ),
        SizedBox(
          width: 100,
          child: TextFormField(
            controller: controller,
            validator: _validateMaterialValue,
            textAlign: TextAlign.right,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              suffixText: '%',
              isDense: true,
              contentPadding: EdgeInsets.only(bottom: 4),
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