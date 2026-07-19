// 카메라 세션과 스캔 화면의 수명주기를 관리하는 진입점입니다.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'models/clothes.dart';
import 'models/clothing_type_option.dart';
import 'models/main_screen_arguments.dart';
import 'services/carbon_api_service.dart';
import 'services/material_catalog_api_service.dart';
import 'services/scan_analysis_service.dart';
import 'services/scan_camera_lifecycle_service.dart';
import 'services/scan_camera_session.dart';
import 'services/scan_capture_service.dart';
import 'services/scan_draft_service.dart';
import 'services/scan_save_service.dart';
import 'utils/clothing_type_catalog.dart';
import 'utils/scan_form_validator.dart';
import 'utils/session_expiry_handler.dart';
import 'widgets/clothing_type_picker_sheet.dart';
import 'widgets/material_input_collection.dart';
import 'widgets/scan_camera_view.dart';
import 'widgets/scan_result_view.dart';

part 'scan/scan_capture_actions.dart';
part 'scan/scan_result_actions.dart';
part 'scan/scan_save_actions.dart';
part 'scan/scan_view_builders.dart';

/// 활성 탭에서만 카메라를 사용하고 촬영 화면과 분석 결과 화면을 전환합니다.
class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key, this.isActive = true});

  final bool isActive;

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> with WidgetsBindingObserver {
  // 스캔 흐름의 현재 단계를 나타냅니다.
  bool _isScanning = false;
  bool _isScanComplete = false;
  bool _isScanFailed = false;
  bool _hasTriedSubmit = false;
  bool _isManualMaterialMode = false;
  bool _isSaving = false;
  bool _hasRequestedMaterialCatalog = false;

  // 촬영 이미지와 분석·서버 응답 원본을 보관합니다.
  File? _selectedImage;
  String _scannedCare = '';
  String? _scanFailureMessage;
  Map<String, double> _originalScannedMaterials = const {};
  int? _serverHealth;
  double? _serverCarbonFootprint;
  double? _serverWeightGram;
  String? _serverCalculationMethod;
  List<MaterialCatalogItem> _materialCatalog = const [];

  // 분석, 촬영, 초안 생성, 계산, 저장 책임은 전용 서비스에 위임합니다.
  final ScanAnalysisService _scanAnalysisService = ScanAnalysisService();
  final CarbonApiService _carbonApiService = CarbonApiService();
  final MaterialCatalogApiService _materialCatalogApiService =
      MaterialCatalogApiService();
  final ScanCaptureService _scanCaptureService = ScanCaptureService();
  final ScanDraftService _scanDraftService = const ScanDraftService();
  final ScanSaveService _scanSaveService = const ScanSaveService();

  // 입력 컨트롤러는 결과 편집 화면과 같은 수명주기를 공유합니다.
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final MaterialInputCollection _materialInputs = MaterialInputCollection();
  final TextEditingController _titleController = TextEditingController();
  ClothingTypeOption _selectedClothingType = ClothingTypeCatalog.defaultOption;
  String _selectedCategory = ClothingTypeCatalog.defaultOption.category;

  // 카메라 세션과 앱·탭 생명주기 연결을 한곳에서 관리합니다.
  final ScanCameraSession _cameraSession = ScanCameraSession();
  late final ScanCameraLifecycleService _cameraLifecycle;

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

  // part 확장에서는 보호 멤버인 setState 대신 이 래퍼로 상태를 갱신합니다.
  void _updateState(VoidCallback callback) => setState(callback);

  bool _canUseCamera() {
    return mounted && widget.isActive && !_isScanComplete && !_isScanning;
  }

  @override
  Widget build(BuildContext context) => _buildScanScreen();
}
