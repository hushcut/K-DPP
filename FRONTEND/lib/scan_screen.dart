import 'dart:io';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:provider/provider.dart';
import 'closet_provider.dart'; // 상태 관리 보관소

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _isScanning = false;
  bool _isScanComplete = false;

  File? _selectedImage;
  final ImagePicker _picker = ImagePicker();

  // 📡 백엔드에서 받아올 데이터를 담을 변수들
  Map<String, dynamic> _scannedMaterials = {}; // 예: {"cotton": 80, "polyester": 20}
  String _scannedCare = ""; // 세탁 지침

  // 📸 카메라 실행 및 서버로 사진 전송 함수
  Future<void> _takePicture() async {
    final XFile? photo = await _picker.pickImage(source: ImageSource.camera);

    if (photo != null) {
      setState(() {
        _selectedImage = File(photo.path);
        _isScanning = true; // 분석 중 애니메이션 시작
      });

      try {
        // 1. 백엔드 팀원이 뚫어준 ngrok 터널 주소로 교체
        var uri = Uri.parse('https://nonmimetically-unplacid-zachery.ngrok-free.dev/api/scan');
        var request = http.MultipartRequest('POST', uri);
        // (ngrok 경고 페이지 무시 패스워드)
        request.headers.addAll({
          'ngrok-skip-browser-warning': 'true',
        });

        request.files.add(await http.MultipartFile.fromPath('image', _selectedImage!.path));

        // 2. 파일 이름표는 이미 'image'로 완벽하게 세팅
        request.files.add(await http.MultipartFile.fromPath('image', _selectedImage!.path));

        // 3. 전송 후 응답 대기
        var streamedResponse = await request.send();
        var response = await http.Response.fromStream(streamedResponse);

        if (response.statusCode == 200) {
          // 4. 응답 성공: JSON 데이터 번역
          final decodedData = json.decode(utf8.decode(response.bodyBytes));
          print("✅ 서버 응답 완료: $decodedData");

          if (decodedData['status'] == 'success') {
            setState(() {
              _isScanning = false;
              _isScanComplete = true;

              // 백엔드의 JSON Key 값에 맞춰서 데이터 꺼내오기
              _scannedMaterials = decodedData['materials'];
              _scannedCare = decodedData['care_instruction'];
            });
          }
        } else {
          print("❌ 서버 에러 발생: ${response.statusCode}");
          _showErrorFallback();
        }
      } catch (e) {
        print("🔌 서버 통신 실패: $e");
        _showErrorFallback();
      }
    }
  }

  // 🚨 서버가 꺼져있을 때 테스트를 위한 임시 조치 함수
  void _showErrorFallback() {
    Future.delayed(const Duration(seconds: 2), () {
      if (!mounted) return;
      setState(() {
        _isScanning = false;
        _isScanComplete = true;
        // 서버 연결 실패 시 임시로 보여줄 가짜 데이터
        _scannedMaterials = {"cotton": 80, "polyester": 20};
        _scannedCare = "30도 이하 물에서 중성세제로 손세탁하세요.";
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('서버 미연결: 임시 결과 화면을 띄웁니다.')),
      );
    });
  }

  // 스캔 초기화
  void _resetScan() {
    setState(() {
      _selectedImage = null;
      _isScanning = false;
      _isScanComplete = false;
      _scannedMaterials = {};
      _scannedCare = "";
    });
  }

  @override
  Widget build(BuildContext context) {
    return _isScanComplete ? _buildResultView() : _buildCameraView();
  }

  // 📷 1. 카메라 뷰 화면
  Widget _buildCameraView() {
    return Container(
      color: Colors.black87,
      width: double.infinity,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text('옷의 케어 라벨을 촬영해 주세요', style: TextStyle(color: Colors.white, fontSize: 16)),
          const SizedBox(height: 30),

          Container(
            width: 250,
            height: 250,
            decoration: BoxDecoration(
              border: Border.all(color: _isScanning ? Colors.greenAccent : Colors.white, width: 2),
              borderRadius: BorderRadius.circular(12),
              color: Colors.white.withOpacity(0.1),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                if (_selectedImage != null)
                  ClipRRect(
                    borderRadius: BorderRadius.circular(10),
                    child: Image.file(_selectedImage!, width: 250, height: 250, fit: BoxFit.cover),
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
                          Text('AI 라벨 분석 중...', style: TextStyle(color: Colors.greenAccent, fontWeight: FontWeight.bold)),
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

  // ✨ 2. 결과 뷰 화면
  Widget _buildResultView() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Center(child: Icon(Icons.check_circle, color: Colors.green, size: 60)),
          const SizedBox(height: 16),
          const Center(child: Text('스캔 완료!', style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold))),
          const SizedBox(height: 32),
          const Text('AI 인식 소재 결과', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),

          // 백엔드에서 받은 소재 리스트를 화면에 그리기
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
                  padding: const EdgeInsets.only(bottom: 8.0),
                  // 키값(예: cotton)을 대문자로 바꾸고, 퍼센티지는 문자열로 바꿈
                  child: _buildMaterialRow(entry.key.toUpperCase(), entry.value.toString()),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 24),

          // 백엔드에서 받은 세탁 지침 띄우기
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Colors.blue.shade50, borderRadius: BorderRadius.circular(12)),
            child: Row(
              children: [
                const Icon(Icons.local_laundry_service, color: Colors.blue),
                const SizedBox(width: 12),
                Expanded(
                  child: Text('AI 분석 세탁 지침:\n$_scannedCare', style: const TextStyle(fontSize: 14, color: Colors.black87)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 40),

          // 옷장 보관소(Provider)에 등록하고 메인으로 돌아가기
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton(
              onPressed: () {
                Provider.of<ClosetProvider>(context, listen: false).addClothes(
                  Clothes(
                    title: '새로 스캔한 의류',
                    category: '상의',
                    health: 100,
                    materials: _scannedMaterials,
                    careInstruction: _scannedCare,
                    carbonFootprint: 0.0, // 아직 서버에서 안 보내주니 0.0으로 임시 처리
                  ),
                );
                Navigator.pushReplacementNamed(context, '/main');
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF4A4EFE),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text('홍길동님의 옷장에 등록하기', style: TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ),
          const SizedBox(height: 12),
          Center(
            child: TextButton(
              onPressed: _resetScan,
              child: const Text('다시 촬영하기', style: TextStyle(color: Colors.grey)),
            ),
          )
        ],
      ),
    );
  }

  // 텍스트 필드 행 (소재 보여주는 위젯)
  Widget _buildMaterialRow(String name, String percentage) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(name, style: const TextStyle(fontSize: 16)),
        SizedBox(
          width: 80,
          child: TextFormField(
            initialValue: percentage,
            textAlign: TextAlign.right,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(suffixText: '%', isDense: true, contentPadding: EdgeInsets.only(bottom: 4)),
          ),
        ),
      ],
    );
  }
}