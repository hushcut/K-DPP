// 로그인 사용자별 옷장, 선택 의류, 인증 세션을 메모리와 로컬 저장소에 동기화하는 파일입니다.
import 'dart:collection';
import 'package:flutter/foundation.dart';
import 'models/analysis_history_record.dart';
import 'models/clothes.dart';
import 'services/auth_session_storage_service.dart';
import 'services/closet_storage_service.dart';

/// 앱 전역에서 사용하는 옷장·사용자 상태를 보관하고 변경 시 화면에 알립니다.
class ClosetProvider with ChangeNotifier {
  final ClosetStorage _storageService;
  final AuthSessionStorage _authSessionStorage;

  // 외부에서는 수정 불가능한 목록으로 노출하고, 모든 변경은 이 Provider를 거칩니다.
  final List<Clothes> _items = [];

  // 저장 실패 롤백이 자신보다 나중에 시작된 변경을 덮어쓰지 않도록,
  // 목록·선택 상태를 바꾸는 모든 작업이 시작 시점에 올립니다.
  int _mutationVersion = 0;

  Clothes? _selectedClothes;
  bool _isLoaded = false;
  String _userName = '홍길동';
  // 설정에서 직접 바꾼 닉네임은 서버 프로필 동기화가 덮어쓰지 않게 표시합니다.
  bool _isUserNameCustomized = false;
  String _userEmail = 'honggildong@kdpp.com';
  String? _closetOwnerEmail;
  AuthSession? _authSession;

  ClosetProvider({
    ClosetStorage? storage,
    AuthSessionStorage? authSessionStorage,
  }) : _storageService = storage ?? ClosetStorageService(),
       _authSessionStorage = authSessionStorage ?? AuthSessionStorageService();

  UnmodifiableListView<Clothes> get items => UnmodifiableListView(_items);

  bool get isLoaded => _isLoaded;

  int get count => _items.length;

  /// 등록 시각이 가장 최근인 의류를 반환하고, 시각이 없는 옛 데이터만 있으면
  /// 이전과 같이 목록의 마지막 항목을 사용합니다.
  Clothes? get latestItem {
    if (_items.isEmpty) return null;

    var latest = _items.last;
    var latestTime = latest.registeredAt;

    for (final item in _items) {
      final registeredAt = item.registeredAt;
      if (registeredAt == null) continue;

      if (latestTime == null || registeredAt.isAfter(latestTime)) {
        latest = item;
        latestTime = registeredAt;
      }
    }

    return latest;
  }

  Clothes? get selectedClothes => _selectedClothes;

  Clothes? get currentReportItem => _selectedClothes ?? latestItem;

  String get userName => _userName;

  String get userEmail => _userEmail;

  String? get accessToken => _authSession?.accessToken;

  bool get isAuthenticated => _authSession != null && !_authSession!.isExpired;

  /// 기기에 표시할 닉네임을 갱신하고 로컬 저장소에도 기록합니다.
  /// 사용자가 직접 바꾼 값이므로 이후 서버 프로필 동기화가 덮어쓰지 않습니다.
  Future<void> setUserName(String value) async {
    final previousName = _userName;
    final wasCustomized = _isUserNameCustomized;
    final trimmed = value.trim();

    _userName = trimmed.isEmpty ? '홍길동' : trimmed;
    _isUserNameCustomized = true;
    notifyListeners();

    try {
      // 이름이 저장된 뒤에만 '직접 수정' 표시를 남겨,
      // 표시만 남고 이름은 안 남는 반쪽 상태를 막습니다.
      await _storageService.saveUserName(_userName);
      await _storageService.saveUserNameCustomized(true);
    } catch (_) {
      _userName = previousName;
      _isUserNameCustomized = wasCustomized;
      notifyListeners();
      rethrow;
    }
  }

  /// 사용자 프로필을 저장하며 계정이 바뀌면 해당 이메일 소유자의 옷장을 불러옵니다.
  Future<void> setUserProfile({
    required String nickname,
    required String email,
  }) async {
    final trimmedNickname = nickname.trim();
    final trimmedEmail = email.trim();
    final normalizedEmail = _normalizeEmail(trimmedEmail);

    if (_authSession != null &&
        normalizedEmail.isNotEmpty &&
        _closetOwnerEmail != normalizedEmail) {
      final previousEmail = _normalizeEmail(_userEmail);

      // 실제로 다른 계정으로 바뀐 경우에는 이전 계정에서 남긴
      // 닉네임 직접 수정 표시를 물려주지 않습니다.
      if (previousEmail != normalizedEmail && _isUserNameCustomized) {
        _isUserNameCustomized = false;
        await _storageService.clearUserNameCustomized();
      }

      await _loadClosetForOwner(
        normalizedEmail,
        migrateLegacyData: previousEmail == normalizedEmail,
      );
    }

    // 기기에서 직접 수정한 닉네임은 유지하고, 그 외에는 서버 닉네임을 따릅니다.
    if (!_isUserNameCustomized) {
      _userName = trimmedNickname.isEmpty ? '홍길동' : trimmedNickname;
    }
    _userEmail = trimmedEmail.isEmpty ? 'honggildong@kdpp.com' : trimmedEmail;
    notifyListeners();

    await Future.wait([
      if (!_isUserNameCustomized) _storageService.saveUserName(_userName),
      _storageService.saveUserEmail(_userEmail),
    ]);
  }

  /// 로그인 응답으로 인증 세션을 만들고 프로필·토큰을 함께 저장합니다.
  Future<void> setAuthenticatedUser({
    required String nickname,
    required String email,
    required String accessToken,
    required int expiresInSeconds,
  }) async {
    final session = AuthSession(
      accessToken: accessToken,
      expiresAt: DateTime.now().add(Duration(seconds: expiresInSeconds)),
    );

    _authSession = session;

    try {
      await setUserProfile(nickname: nickname, email: email);
      await _authSessionStorage.saveSession(session);
    } catch (error) {
      // 절반만 로그인된 상태가 남지 않도록 메모리와 저장소의 세션을 함께 되돌립니다.
      _authSession = null;

      try {
        await _authSessionStorage.clearSession();
      } catch (clearError) {
        debugPrint('로그인 롤백 중 세션 정리에 실패했습니다: $clearError');
      }

      notifyListeners();
      rethrow;
    }
  }

  /// 메모리의 사용자·옷장 상태와 기기에 저장된 인증 정보를 초기화합니다.
  Future<void> logout() async {
    _mutationVersion++;
    _items.clear();
    _selectedClothes = null;
    _closetOwnerEmail = null;
    _userName = '홍길동';
    _isUserNameCustomized = false;
    _userEmail = 'honggildong@kdpp.com';
    _authSession = null;
    notifyListeners();
    await Future.wait([
      _storageService.clearUserName(),
      _storageService.clearUserNameCustomized(),
      _storageService.clearUserEmail(),
      _authSessionStorage.clearSession(),
    ]);
  }

  /// 현재 옷장에 등록된 의류의 탄소 배출 추정값 합계입니다.
  double get totalCarbonFootprint {
    return _items.fold(0.0, (sum, item) => sum + item.carbonFootprint);
  }

  /// 등록 의류가 없으면 0, 있으면 건강도 평균을 반환합니다.
  double get averageHealth {
    if (_items.isEmpty) return 0.0;
    final total = _items.fold<int>(0, (sum, item) => sum + item.health);
    return total / _items.length;
  }

  /// 저장된 프로필과 세션을 복원하고 유효한 계정의 전용 옷장을 불러옵니다.
  Future<void> loadFromStorage() async {
    final savedUserName = await _storageService.loadUserName();
    final savedUserEmail = await _storageService.loadUserEmail();
    AuthSession? savedAuthSession;

    try {
      savedAuthSession = await _authSessionStorage.loadSession();
    } catch (error, stackTrace) {
      debugPrint('인증 세션을 불러오지 못했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    if (savedUserName != null && savedUserName.trim().isNotEmpty) {
      _userName = savedUserName.trim();
    }

    _isUserNameCustomized = await _storageService.loadUserNameCustomized();

    if (savedUserEmail != null && savedUserEmail.trim().isNotEmpty) {
      _userEmail = savedUserEmail.trim();
    }

    if (savedAuthSession != null && !savedAuthSession.isExpired) {
      _authSession = savedAuthSession;
      final normalizedEmail = _normalizeEmail(savedUserEmail ?? '');

      if (normalizedEmail.isNotEmpty) {
        await _loadClosetForOwner(normalizedEmail, migrateLegacyData: true);
      } else {
        _clearClosetMemory();
      }
    } else {
      _authSession = null;
      _clearClosetMemory();

      if (savedAuthSession != null) {
        await _authSessionStorage.clearSession();
      }
    }

    _isLoaded = true;
    notifyListeners();
  }

  // 로그인 계정이 있으면 계정별 공간에, 없으면 기존 공용 공간에 옷장을 저장합니다.
  Future<void> _persist() async {
    final ownerEmail = _closetOwnerEmail;

    if (ownerEmail == null) {
      await _storageService.saveClothesList(_items);
      return;
    }

    await _storageService.saveClothesListFor(ownerEmail, _items);
  }

  /// 새 의류를 목록과 현재 리포트 대상으로 등록한 뒤 저장합니다.
  /// 저장이 실패하면 화면과 디스크가 어긋나지 않도록 목록에서 되돌립니다.
  Future<void> addClothes(Clothes newClothes) async {
    final mutationVersion = ++_mutationVersion;
    final previousSelected = _selectedClothes;

    _items.add(newClothes);
    _selectedClothes = newClothes;
    notifyListeners();

    try {
      await _persist();
    } catch (_) {
      // 더 새로운 변경이 이미 반영됐다면 낡은 상태로 되돌리지 않습니다.
      if (mutationVersion == _mutationVersion) {
        _items.remove(newClothes);
        _selectedClothes = previousSelected;
        notifyListeners();
      }
      rethrow;
    }
  }

  /// 객체 또는 서버 저장 ID로 대상 의류를 찾아 수정하고 선택 상태도 교체합니다.
  /// 저장이 실패하면 화면과 디스크가 어긋나지 않도록 이전 값으로 되돌립니다.
  Future<bool> updateClothes(Clothes target, Clothes updated) async {
    var index = _items.indexOf(target);

    if (index == -1 && target.savedResultId != null) {
      index = _items.indexWhere(
        (item) => item.savedResultId == target.savedResultId,
      );
    }

    if (index == -1) {
      return false;
    }

    final mutationVersion = ++_mutationVersion;
    final previous = _items[index];
    final previousSelected = _selectedClothes;

    _items[index] = updated;

    final isSelectedTarget =
        identical(_selectedClothes, target) ||
        _selectedClothes == target ||
        (target.savedResultId != null &&
            _selectedClothes?.savedResultId == target.savedResultId);

    if (isSelectedTarget) {
      _selectedClothes = updated;
    }

    notifyListeners();

    try {
      await _persist();
    } catch (_) {
      if (mutationVersion == _mutationVersion) {
        _items[index] = previous;
        _selectedClothes = previousSelected;
        notifyListeners();
      }
      rethrow;
    }

    return true;
  }

  /// 서버 분석 이력과 로컬 항목을 저장 ID로 연결해 달라진 탄소·소재 값을 반영합니다.
  Future<int> synchronizeServerHistory(
    List<AnalysisHistoryRecord> history,
  ) async {
    if (history.isEmpty || _items.isEmpty) {
      return 0;
    }

    final recordsById = {for (final record in history) record.id: record};
    var updatedCount = 0;

    for (var index = 0; index < _items.length; index++) {
      final current = _items[index];
      final savedResultId = current.savedResultId;

      if (savedResultId == null) {
        continue;
      }

      final record = recordsById[savedResultId];

      if (record == null || _matchesServerRecord(current, record)) {
        continue;
      }

      // copyWith는 null을 "유지"로 해석해 서버의 null 범위값을 지우지 못하므로,
      // 서버 기록 값을 그대로 반영하도록 새 인스턴스를 직접 만듭니다.
      final updated = Clothes(
        title: current.title,
        category: current.category,
        health: current.health,
        materials: Map<String, double>.from(record.materials),
        careInstruction: current.careInstruction,
        carbonFootprint: record.carbonFootprint,
        carbonFootprintSource: CarbonFootprintSource.server,
        carbonFootprintMin: record.carbonFootprintMin,
        carbonFootprintMax: record.carbonFootprintMax,
        minWeightGram: record.minWeightGram,
        maxWeightGram: record.maxWeightGram,
        savedResultId: current.savedResultId,
        registeredAt: current.registeredAt,
      );

      if (updatedCount == 0) {
        _mutationVersion++;
      }

      _items[index] = updated;

      if (identical(_selectedClothes, current)) {
        _selectedClothes = updated;
      }

      updatedCount++;
    }

    if (updatedCount > 0) {
      notifyListeners();
      await _persist();
    }

    return updatedCount;
  }

  bool _matchesServerRecord(Clothes clothes, AnalysisHistoryRecord record) {
    return mapEquals(clothes.materials, record.materials) &&
        clothes.carbonFootprint == record.carbonFootprint &&
        clothes.carbonFootprintSource == CarbonFootprintSource.server &&
        clothes.carbonFootprintMin == record.carbonFootprintMin &&
        clothes.carbonFootprintMax == record.carbonFootprintMax &&
        clothes.minWeightGram == record.minWeightGram &&
        clothes.maxWeightGram == record.maxWeightGram;
  }

  // 계정 옷장을 불러오고, 요청이 있으면 예전 공용 옷장을 합친 뒤 과거 샘플 항목은 제거합니다.
  Future<void> _loadClosetForOwner(
    String ownerEmail, {
    required bool migrateLegacyData,
  }) async {
    final normalizedEmail = _normalizeEmail(ownerEmail);

    if (normalizedEmail.isEmpty) {
      _clearClosetMemory();
      return;
    }

    final hasAccountData = await _storageService.hasSavedClothesListFor(
      normalizedEmail,
    );
    final accountItems = hasAccountData
        ? await _storageService.loadClothesListFor(normalizedEmail)
        : const <Clothes>[];

    // 예전 공용 옷장은 계정 옷장에 실제로 합쳐 저장한 뒤에만 비워서 유실을 막습니다.
    var shouldClearLegacyData = false;
    var legacyItems = const <Clothes>[];

    if (migrateLegacyData && await _storageService.hasSavedClothesList()) {
      legacyItems = await _storageService.loadClothesList();
      shouldClearLegacyData = true;
    }

    final savedItems = [...accountItems, ...legacyItems];
    final migratedItems = savedItems
        .where((item) => !_isLegacySampleClothes(item))
        .toList();

    _mutationVersion++;
    _closetOwnerEmail = normalizedEmail;
    _items
      ..clear()
      ..addAll(migratedItems);
    _selectedClothes = _items.isNotEmpty ? _items.last : null;

    if (!hasAccountData ||
        shouldClearLegacyData ||
        migratedItems.length != savedItems.length) {
      await _storageService.saveClothesListFor(normalizedEmail, _items);
    }

    if (shouldClearLegacyData) {
      await _storageService.clearClothesList();
    }
  }

  void _clearClosetMemory() {
    _mutationVersion++;
    _items.clear();
    _selectedClothes = null;
    _closetOwnerEmail = null;
  }

  String _normalizeEmail(String value) {
    return value.trim().toLowerCase();
  }

  bool _isLegacySampleClothes(Clothes clothes) {
    final isOrganicCottonSample =
        clothes.title == '오가닉 코튼 맨투맨' &&
        clothes.category == '상의' &&
        clothes.health == 65 &&
        mapEquals(clothes.materials, const {'cotton': 100.0}) &&
        clothes.careInstruction == '30도 이하 물에서 세탁하세요.' &&
        clothes.carbonFootprint == 15.5 &&
        clothes.savedResultId == null;

    final isDenimSample =
        clothes.title == '오래된 데님 팬츠' &&
        clothes.category == '하의' &&
        clothes.health == 10 &&
        mapEquals(clothes.materials, const {
          'cotton': 98.0,
          'polyurethane': 2.0,
        }) &&
        clothes.careInstruction == '단독 세탁 권장' &&
        clothes.carbonFootprint == 25.0 &&
        clothes.savedResultId == null;

    return isOrganicCottonSample || isDenimSample;
  }

  /// 상세 리포트에서 사용할 현재 의류를 선택합니다.
  void selectClothes(Clothes clothes) {
    _selectedClothes = clothes;
    notifyListeners();
  }

  /// 한 의류를 삭제하고 선택 대상이 사라지면 마지막 항목으로 보정합니다.
  /// 같은 인스턴스가 없으면 서버 저장 ID로 다시 찾고, 실제 삭제 여부를 반환하며,
  /// 저장이 실패하면 목록을 삭제 전으로 되돌립니다.
  Future<bool> removeClothes(Clothes target) async {
    var index = _items.indexOf(target);

    if (index == -1 && target.savedResultId != null) {
      index = _items.indexWhere(
        (item) => item.savedResultId == target.savedResultId,
      );
    }

    if (index == -1) {
      return false;
    }

    final mutationVersion = ++_mutationVersion;
    final removed = _items.removeAt(index);
    final previousSelected = _selectedClothes;

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (identical(_selectedClothes, removed) ||
        _selectedClothes == target) {
      _selectedClothes = _items.last;
    }

    notifyListeners();

    try {
      await _persist();
    } catch (_) {
      if (mutationVersion == _mutationVersion) {
        _items.insert(index, removed);
        _selectedClothes = previousSelected;
        notifyListeners();
      }
      rethrow;
    }

    return true;
  }

  /// 여러 의류를 한 번에 삭제해 알림과 저장 작업을 한 차례만 수행합니다.
  /// 저장이 실패하면 목록과 선택 상태를 삭제 전으로 되돌립니다.
  Future<void> removeClothesBatch(List<Clothes> targets) async {
    final mutationVersion = ++_mutationVersion;
    final previousItems = List<Clothes>.from(_items);
    final previousSelected = _selectedClothes;
    final targetSet = targets.toSet();
    _items.removeWhere((item) => targetSet.contains(item));

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes != null &&
        targetSet.contains(_selectedClothes)) {
      _selectedClothes = _items.last;
    }

    notifyListeners();

    try {
      await _persist();
    } catch (_) {
      if (mutationVersion == _mutationVersion) {
        _items
          ..clear()
          ..addAll(previousItems);
        _selectedClothes = previousSelected;
        notifyListeners();
      }
      rethrow;
    }
  }

  /// 사용자가 재배치한 전체 순서를 적용하고 계정별 옷장에 저장합니다.
  /// 저장이 실패하면 다음 실행과 어긋나지 않도록 이전 순서로 되돌립니다.
  Future<void> setCustomOrder(List<Clothes> newOrder) async {
    final mutationVersion = ++_mutationVersion;
    final previousOrder = List<Clothes>.from(_items);
    final previousSelected = _selectedClothes;

    _items
      ..clear()
      ..addAll(newOrder);

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes != null && !_items.contains(_selectedClothes)) {
      _selectedClothes = _items.last;
    }

    notifyListeners();

    try {
      await _persist();
    } catch (_) {
      if (mutationVersion == _mutationVersion) {
        _items
          ..clear()
          ..addAll(previousOrder);
        _selectedClothes = previousSelected;
        notifyListeners();
      }
      rethrow;
    }
  }

  /// 현재 계정의 모든 의류와 선택 상태를 지웁니다.
  Future<void> clearAllClothes() async {
    _mutationVersion++;
    _items.clear();
    _selectedClothes = null;
    notifyListeners();

    final ownerEmail = _closetOwnerEmail;
    if (ownerEmail == null) {
      await _storageService.clearClothesList();
      return;
    }

    await _storageService.clearClothesListFor(ownerEmail);
  }
}
