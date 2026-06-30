import 'dart:collection';
import 'package:flutter/foundation.dart';
import 'models/analysis_history_record.dart';
import 'models/clothes.dart';
import 'services/auth_session_storage_service.dart';
import 'services/closet_storage_service.dart';

class ClosetProvider with ChangeNotifier {
  final ClosetStorage _storageService;
  final AuthSessionStorage _authSessionStorage;

  final List<Clothes> _items = [];

  Clothes? _selectedClothes;
  bool _isLoaded = false;
  String _userName = '홍길동';
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

  Clothes? get latestItem => _items.isEmpty ? null : _items.last;

  Clothes? get selectedClothes => _selectedClothes;

  Clothes? get currentReportItem => _selectedClothes ?? latestItem;

  String get userName => _userName;

  String get userEmail => _userEmail;

  String? get accessToken => _authSession?.accessToken;

  bool get isAuthenticated => _authSession != null && !_authSession!.isExpired;

  Future<void> setUserName(String value) async {
    final trimmed = value.trim();
    _userName = trimmed.isEmpty ? '홍길동' : trimmed;
    notifyListeners();
    await _storageService.saveUserName(_userName);
  }

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
      await _loadClosetForOwner(
        normalizedEmail,
        migrateLegacyData: previousEmail == normalizedEmail,
      );
    }

    _userName = trimmedNickname.isEmpty ? '홍길동' : trimmedNickname;
    _userEmail = trimmedEmail.isEmpty ? 'honggildong@kdpp.com' : trimmedEmail;
    notifyListeners();

    await Future.wait([
      _storageService.saveUserName(_userName),
      _storageService.saveUserEmail(_userEmail),
    ]);
  }

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
    await Future.wait([
      setUserProfile(nickname: nickname, email: email),
      _authSessionStorage.saveSession(session),
    ]);
  }

  Future<void> logout() async {
    _items.clear();
    _selectedClothes = null;
    _closetOwnerEmail = null;
    _userName = '홍길동';
    _userEmail = 'honggildong@kdpp.com';
    _authSession = null;
    notifyListeners();
    await Future.wait([
      _storageService.clearUserName(),
      _storageService.clearUserEmail(),
      _authSessionStorage.clearSession(),
    ]);
  }

  double get totalCarbonFootprint {
    return _items.fold(0.0, (sum, item) => sum + item.carbonFootprint);
  }

  double get averageHealth {
    if (_items.isEmpty) return 0.0;
    final total = _items.fold<int>(0, (sum, item) => sum + item.health);
    return total / _items.length;
  }

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

  Future<void> _persist() async {
    final ownerEmail = _closetOwnerEmail;

    if (ownerEmail == null) {
      await _storageService.saveClothesList(_items);
      return;
    }

    await _storageService.saveClothesListFor(ownerEmail, _items);
  }

  Future<void> addClothes(Clothes newClothes) async {
    _items.add(newClothes);
    _selectedClothes = newClothes;
    notifyListeners();
    await _persist();
  }

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
    await _persist();
    return true;
  }

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

      final updated = current.copyWith(
        materials: Map<String, double>.from(record.materials),
        carbonFootprint: record.carbonFootprint,
        carbonFootprintSource: CarbonFootprintSource.server,
        carbonFootprintMin: record.carbonFootprintMin,
        carbonFootprintMax: record.carbonFootprintMax,
        minWeightGram: record.minWeightGram,
        maxWeightGram: record.maxWeightGram,
      );

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
    List<Clothes> savedItems;

    if (hasAccountData) {
      savedItems = await _storageService.loadClothesListFor(normalizedEmail);
    } else if (migrateLegacyData &&
        await _storageService.hasSavedClothesList()) {
      savedItems = await _storageService.loadClothesList();
    } else {
      savedItems = const [];
    }

    final migratedItems = savedItems
        .where((item) => !_isLegacySampleClothes(item))
        .toList();

    _closetOwnerEmail = normalizedEmail;
    _items
      ..clear()
      ..addAll(migratedItems);
    _selectedClothes = _items.isNotEmpty ? _items.last : null;

    if (!hasAccountData || migratedItems.length != savedItems.length) {
      await _storageService.saveClothesListFor(normalizedEmail, _items);
    }

    if (migrateLegacyData && await _storageService.hasSavedClothesList()) {
      await _storageService.clearClothesList();
    }
  }

  void _clearClosetMemory() {
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

  void selectClothes(Clothes clothes) {
    _selectedClothes = clothes;
    notifyListeners();
  }

  Future<void> removeClothes(Clothes target) async {
    _items.remove(target);

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes == target) {
      _selectedClothes = _items.last;
    }

    notifyListeners();
    await _persist();
  }

  Future<void> removeClothesBatch(List<Clothes> targets) async {
    final targetSet = targets.toSet();
    _items.removeWhere((item) => targetSet.contains(item));

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes != null &&
        targetSet.contains(_selectedClothes)) {
      _selectedClothes = _items.last;
    }

    notifyListeners();
    await _persist();
  }

  Future<void> setCustomOrder(List<Clothes> newOrder) async {
    _items
      ..clear()
      ..addAll(newOrder);

    if (_items.isEmpty) {
      _selectedClothes = null;
    } else if (_selectedClothes != null && !_items.contains(_selectedClothes)) {
      _selectedClothes = _items.last;
    }

    notifyListeners();
    await _persist();
  }

  Future<void> clearAllClothes() async {
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
