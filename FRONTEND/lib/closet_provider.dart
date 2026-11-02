// 로그인 사용자별 옷장, 선택 의류, 인증 세션을 메모리와 로컬 저장소에 동기화하는 파일입니다.
import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'models/analysis_history_record.dart';
import 'models/closet_backup_state.dart';
import 'models/closet_sort_option.dart';
import 'models/clothes.dart';
import 'services/auth_api_service.dart';
import 'services/auth_session_storage_service.dart';
import 'services/closet_backup_api_service.dart';
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
  // 이메일이 없는 계정(카카오)과 로그아웃 상태에서는 null 입니다.
  String? _userEmail;
  int? _userId;
  List<String> _loginMethods = const [];
  // 계정별 옷장의 주인 키입니다([_closetOwnerKeyFor]).
  String? _closetOwnerKey;
  // 이번 실행에서 로그아웃한 적이 있으면 true 입니다. 그 뒤 주인 없이 들어온 저장은 공용 옷장 칸에
  // 쓰지 않습니다 — 공용 칸은 다음에 앱을 켠 이메일 계정 옷장에 합쳐지기 때문입니다(DECISIONS 2026-10-14).
  // 로그인 중엔 계정 칸에 쓰므로 이 값은 주인이 없을 때만 봅니다.
  bool _hasSignedOut = false;
  ClosetSortOption _closetSortOption = ClosetSortOption.eco;

  // 정렬 기준은 목록·선택 상태와 무관하므로 별도 카운터를 씁니다.
  // _mutationVersion을 함께 올리면 진행 중이던 옷장 저장의 롤백이 건너뛰어집니다.
  int _sortMutationVersion = 0;
  AuthSession? _authSession;

  // 옷장 서버 백업(DECISIONS 242)입니다. null 이면 백업을 모두 건너뜁니다(시험 기본값).
  final ClosetBackupApi? _backupApi;

  /// 옷장 변경을 모아 서버에 한 번에 올리기까지 기다리는 시간입니다.
  final Duration backupUploadDelay;

  /// 서버에 닿지 못한 첫 맞춤을 옷장이 바뀔 때 다시 하기까지 두는 최소 간격입니다.
  final Duration firstSyncRetryInterval;

  final DateTime Function() _now;

  Timer? _backupUploadTimer;
  bool _isBackupUploading = false;
  // 올리는 중에 또 바뀌면 끝난 뒤 한 번 더 올립니다.
  bool _isBackupUploadQueued = false;
  // 첫 맞춤 뒤 처음 올릴 때의 표시입니다. 그 사이 기기 변경이 없는데 409 가 오면 덮지 않고
  // 한 번 더 받아 합칩니다 — 첫 맞춤과 업로드 사이에 다른 폰이 넣은 옷이 빠지지 않게.
  ({String ownerKey, int mutationVersion})? _firstSyncUpload;
  // 첫 맞춤이 진행 중인 옷장 주인들입니다. 주인마다 따로 두어, A 의 받기가 걸린 사이 로그인한 B 가 건너뛰어지지 않게 합니다.
  final Set<String> _firstSyncRunningOwnerKeys = {};
  // 탈퇴 대화상자가 떠 있는 동안 백업 예약을 멈춥니다([cancelScheduledClosetBackup]).
  bool _isBackupPaused = false;
  // 탈퇴 정리 중인 옷장 주인입니다. 그사이 끝난 받기가 지운 옷장·상태를 되살리지 않게 합니다.
  String? _purgingOwnerKey;
  // 첫 맞춤에서 서버에 닿지 못한 옷장 주인입니다. 그 옷장이 바뀌면 첫 맞춤을 다시 해 봅니다.
  String? _firstSyncRetryOwnerKey;
  DateTime? _lastFirstSyncAttemptAt;
  Timer? _firstSyncRetryTimer;
  // 이번 실행에서 서버가 거절해(413·422 등) 백업을 멈춘 옷장 주인들입니다.
  final Set<String> _backupRejectedOwnerKeys = {};
  // 백업 요청이 401 을 받은 토큰들입니다. 같은 토큰으로는 이번 실행에 다시 보내지 않습니다.
  final Set<String> _backupUnauthorizedTokens = {};
  final StreamController<int> _closetRestoreController =
      StreamController<int>.broadcast();
  bool _isDisposed = false;

  ClosetProvider({
    ClosetStorage? storage,
    AuthSessionStorage? authSessionStorage,
    ClosetBackupApi? backupApi,
    this.backupUploadDelay = const Duration(seconds: 2),
    this.firstSyncRetryInterval = const Duration(seconds: 30),
    DateTime Function()? now,
  }) : _storageService = storage ?? ClosetStorageService(),
       _authSessionStorage = authSessionStorage ?? AuthSessionStorageService(),
       _backupApi = backupApi,
       _now = now ?? DateTime.now;

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

  /// 표시용 이메일입니다. 이메일이 없으면 기본값을 돌려주므로,
  /// 계정에 이메일이 있는지는 [accountEmail] 로 봅니다.
  String get userEmail => _userEmail ?? 'honggildong@kdpp.com';

  /// 이 계정의 이메일입니다. 이메일이 없는 계정(카카오)이면 null 입니다.
  String? get accountEmail => _userEmail;

  /// 이 계정으로 로그인하는 방법(`user.login_methods`)입니다.
  UnmodifiableListView<String> get loginMethods =>
      UnmodifiableListView(_loginMethods);

  /// 비밀번호로 로그인하는 계정인지 — 비밀번호 변경·탈퇴 확인 방식을 고릅니다.
  bool get hasPasswordLogin => _loginMethods.contains(LoginMethod.password);

  String? get accessToken => _authSession?.accessToken;

  /// 지금 옷장 주인 키입니다. 로그아웃 상태면 null 입니다.
  ///
  /// 서버 응답을 기다리는 사이 계정이 바뀔 수 있는 저장(스캔 저장)은 시작할 때 이 값을 잡아
  /// 두었다가 [addClothesForOwner] 에 넘깁니다.
  String? get closetOwnerKey => _closetOwnerKey;

  /// 옷장 목록에 적용 중인 정렬 기준입니다. 기기 단위 표시 설정이라
  /// 계정을 바꾸거나 로그아웃해도 유지됩니다.
  ClosetSortOption get closetSortOption => _closetSortOption;

  bool get isAuthenticated => _authSession != null && !_authSession!.isExpired;

  /// 서버 백업에서 옷을 되살릴 때마다 되살린 벌 수를 보냅니다. 화면은 이것으로 배너를 띄웁니다.
  Stream<int> get closetRestores => _closetRestoreController.stream;

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

  /// 사용자 프로필을 저장하며 계정이 바뀌면 그 계정의 옷장을 불러옵니다.
  ///
  /// 옷장 주인은 이메일 계정이면 이메일, 이메일이 없는 계정(카카오)이면 [userId] 입니다.
  /// 로그인 중인데 둘 다 없으면 [StateError] 를 던집니다 — 주인 없이 저장하면 공용 옷장에
  /// 들어가 같은 기기의 다음 이메일 계정 옷장에 합쳐지기 때문입니다.
  /// [loginMethods] 를 주지 않으면 이메일이 있을 때 비밀번호 계정으로 봅니다.
  Future<void> setUserProfile({
    required String nickname,
    required String? email,
    int? userId,
    List<String>? loginMethods,
  }) async {
    final trimmedNickname = nickname.trim();
    final trimmedEmail = email?.trim() ?? '';
    final accountEmail = trimmedEmail.isEmpty ? null : trimmedEmail;
    final ownerKey = _closetOwnerKeyFor(email: accountEmail, userId: userId);

    if (_authSession != null && ownerKey == null) {
      throw StateError('옷장 주인을 정할 이메일이나 사용자 id 가 없습니다.');
    }

    if (_authSession != null && _closetOwnerKey != ownerKey) {
      final previousOwnerKey = _closetOwnerKeyFor(
        email: _userEmail,
        userId: _userId,
      );

      // 실제로 다른 계정으로 바뀐 경우에는 이전 계정에서 남긴
      // 닉네임 직접 수정 표시를 물려주지 않습니다.
      if (previousOwnerKey != ownerKey && _isUserNameCustomized) {
        _isUserNameCustomized = false;
        await _storageService.clearUserNameCustomized();
      }

      // 예전 공용 옷장은 계정이 생기기 전 이메일 사용자의 것이라 이메일 계정에만 합칩니다.
      await _loadClosetForOwner(
        ownerKey!,
        migrateLegacyData: accountEmail != null && previousOwnerKey == ownerKey,
      );
    }

    // 기기에서 직접 수정한 닉네임은 유지하고, 그 외에는 서버 닉네임을 따릅니다.
    if (!_isUserNameCustomized) {
      _userName = trimmedNickname.isEmpty ? '홍길동' : trimmedNickname;
    }
    _userEmail = accountEmail;
    _userId = userId;
    _loginMethods = List.unmodifiable(
      loginMethods ?? _defaultLoginMethods(accountEmail),
    );
    notifyListeners();

    await Future.wait([
      if (!_isUserNameCustomized) _storageService.saveUserName(_userName),
      if (accountEmail == null)
        _storageService.clearUserEmail()
      else
        _storageService.saveUserEmail(accountEmail),
      if (userId == null)
        _storageService.clearUserId()
      else
        _storageService.saveUserId(userId),
      _storageService.saveLoginMethods(_loginMethods),
    ]);
  }

  /// 로그인 응답으로 인증 세션을 만들고 프로필·토큰을 함께 저장합니다.
  Future<void> setAuthenticatedUser({
    required String nickname,
    required String? email,
    int? userId,
    List<String>? loginMethods,
    required String accessToken,
    required int expiresInSeconds,
  }) async {
    final session = AuthSession(
      accessToken: accessToken,
      expiresAt: DateTime.now().add(Duration(seconds: expiresInSeconds)),
    );

    _authSession = session;

    try {
      await setUserProfile(
        nickname: nickname,
        email: email,
        userId: userId,
        loginMethods: loginMethods,
      );
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

  /// 회원 탈퇴 뒤 이 기기에 남은 계정 전용 옷장까지 지우고 로그아웃 상태로 되돌립니다.
  ///
  /// 로그아웃은 다시 로그인할 것을 전제로 계정별 옷장을 남겨 두므로,
  /// 탈퇴에서는 그 데이터까지 지워야 다른 사람이 같은 기기를 써도 남지 않습니다.
  ///
  /// 옷장 삭제가 실패해도 **세션 정리는 반드시 끝냅니다.** 삭제된 계정의 토큰이
  /// 기기에 남으면 다음 실행에서 이미 없는 계정으로 복원을 시도하기 때문입니다.
  /// 실패는 호출부가 사용자에게 알릴 수 있도록 마지막에 다시 던집니다.
  Future<void> purgeAccountData() async {
    // logout()이 이메일·사용자 id 를 지우기 때문에 먼저 읽어 둡니다.
    final ownerKey =
        _closetOwnerKey ??
        _closetOwnerKeyFor(email: _userEmail, userId: _userId);

    Object? closetClearError;
    StackTrace? closetClearStackTrace;

    _cancelBackupTimers();
    _purgingOwnerKey = ownerKey;

    if (ownerKey != null) {
      try {
        await _storageService.clearClothesListFor(ownerKey);
      } catch (error, stackTrace) {
        closetClearError = error;
        closetClearStackTrace = stackTrace;
      }

      // 옷장 키가 지워지면 다음 로드가 상태도 지우지만, 여기서도 지워 남지 않게 합니다.
      try {
        await _storageService.clearClosetBackupStateFor(ownerKey);
      } catch (error, stackTrace) {
        closetClearError ??= error;
        closetClearStackTrace ??= stackTrace;
      }
    }

    try {
      await logout();
    } finally {
      _purgingOwnerKey = null;
    }

    if (closetClearError != null) {
      Error.throwWithStackTrace(
        closetClearError,
        closetClearStackTrace ?? StackTrace.current,
      );
    }
  }

  /// 메모리의 사용자·옷장 상태와 기기에 저장된 인증 정보를 초기화합니다.
  ///
  /// 서버 백업과 맞춘 상태는 남겨, 같은 계정으로 다시 로그인하면 받아 합치지 않고 이어서 올립니다.
  Future<void> logout() async {
    _cancelBackupTimers();
    _isBackupPaused = false;
    _firstSyncRetryOwnerKey = null;
    _mutationVersion++;
    _items.clear();
    _selectedClothes = null;
    _closetOwnerKey = null;
    _hasSignedOut = true;
    _userName = '홍길동';
    _isUserNameCustomized = false;
    _userEmail = null;
    _userId = null;
    _loginMethods = const [];
    _authSession = null;
    notifyListeners();
    await Future.wait([
      _storageService.clearUserName(),
      _storageService.clearUserNameCustomized(),
      _storageService.clearUserEmail(),
      _storageService.clearUserId(),
      _storageService.clearLoginMethods(),
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

  /// 정렬 기준을 즉시 반영한 뒤 다음 실행을 위해 저장합니다.
  ///
  /// 저장에 실패하면 이전 값으로 되돌리고 호출부에 알립니다. 다만 되돌리는 사이
  /// 더 새로운 선택이 들어왔다면 그 선택을 덮어쓰지 않고, 호출부에도 알리지
  /// 않습니다. 이미 버려진 선택의 실패를 사용자에게 알리면 화면에 적용된 기준과
  /// 어긋나는 안내가 되기 때문입니다.
  Future<void> setClosetSortOption(ClosetSortOption option) async {
    if (_closetSortOption == option) return;

    final mutationVersion = ++_sortMutationVersion;
    final previousOption = _closetSortOption;
    _closetSortOption = option;
    notifyListeners();

    try {
      await _storageService.saveClosetSortOption(option);
    } catch (error, stackTrace) {
      debugPrint('정렬 기준을 저장하지 못했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (mutationVersion == _sortMutationVersion) {
        _closetSortOption = previousOption;
        notifyListeners();
        rethrow;
      }
    }
  }

  /// 저장된 프로필과 세션을 복원하고 유효한 계정의 전용 옷장을 불러옵니다.
  Future<void> loadFromStorage() async {
    // 서로 독립적인 저장소 읽기는 병렬로 실행해 시작 시간을 줄입니다.
    final (
      savedUserName,
      savedUserEmail,
      savedUserId,
      savedLoginMethods,
      savedNameCustomized,
      savedSortOption,
    ) = await (
      _storageService.loadUserName(),
      _storageService.loadUserEmail(),
      _storageService.loadUserId(),
      _storageService.loadLoginMethods(),
      _storageService.loadUserNameCustomized(),
      _storageService.loadClosetSortOption(),
    ).wait;

    _closetSortOption = savedSortOption;
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

    _isUserNameCustomized = savedNameCustomized;

    if (savedUserEmail != null && savedUserEmail.trim().isNotEmpty) {
      _userEmail = savedUserEmail.trim();
    }

    _userId = savedUserId;
    // 로그인 방법을 저장하기 전 판에서 로그인한 기기는 이메일 계정뿐입니다.
    _loginMethods = List.unmodifiable(
      savedLoginMethods ?? _defaultLoginMethods(_userEmail),
    );

    if (savedAuthSession != null && !savedAuthSession.isExpired) {
      _authSession = savedAuthSession;
      final ownerKey = _closetOwnerKeyFor(email: _userEmail, userId: _userId);

      if (ownerKey != null) {
        await _loadClosetForOwner(
          ownerKey,
          migrateLegacyData: _userEmail != null,
        );
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
  // 로그아웃한 뒤에는 공용 공간에도 쓰지 않고 실패로 돌려, 부른 쪽이 목록을 되돌리게 합니다.
  Future<void> _persist() async {
    final ownerKey = _closetOwnerKey;

    if (ownerKey == null) {
      if (_hasSignedOut) {
        throw StateError('로그아웃한 뒤에는 옷장을 저장하지 않습니다.');
      }
      // 로그인 중인데 주인이 없으면 공용 칸에 들어가 다음 이메일 계정 옷장에 합쳐지고,
      // 이 계정의 서버 백업에도 오르지 않습니다([setUserProfile] 과 같은 원칙).
      if (_authSession != null) {
        throw StateError('로그인 중인데 옷장 주인이 없어 저장하지 않습니다.');
      }
      await _storageService.saveClothesList(_items);
      return;
    }

    await _storageService.saveClothesListFor(ownerKey, _items);
    _onAccountClosetSaved(ownerKey);
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

  /// [ownerKey] 계정 옷장에 새 의류를 넣고, 지금 옷장에 넣었으면 true 를 돌려줍니다.
  ///
  /// [ownerKey] 는 저장을 시작할 때 잡아 둔 [closetOwnerKey] 입니다. 기다리는 사이 로그아웃했거나
  /// 다른 계정으로 바뀌었으면 지금 옷장은 건드리지 않고 기기에 저장된 [ownerKey] 옷장에만 더한 뒤
  /// false 를 돌려줍니다 — 서버엔 이미 그 계정 기록이 있으니 다시 로그인하면 보이게 합니다.
  /// 그 옷장이 기기에 없으면(탈퇴로 지워짐) 어디에도 넣지 않습니다(DECISIONS 2026-10-14).
  Future<bool> addClothesForOwner(String? ownerKey, Clothes newClothes) async {
    if (ownerKey == _closetOwnerKey) {
      await addClothes(newClothes);
      return true;
    }

    // 로그인 전에 시작한 저장은 넣을 계정 옷장이 없습니다.
    if (ownerKey == null) return false;

    final (savedItems, status) = await _storageService
        .loadClothesListWithStatusFor(ownerKey);
    if (status == ClosetLoadStatus.missing) return false;

    // 망가진 값을 읽은 목록으로 덮으므로, 그 계정의 백업 상태를 먼저 지워 다음 동기화가 합치기가 되게 합니다.
    if (status == ClosetLoadStatus.corrupt) {
      await _storageService.clearClosetBackupStateFor(ownerKey);
    }

    await _storageService.saveClothesListFor(ownerKey, [
      ...savedItems,
      newClothes,
    ]);
    return false;
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

    // 저장 실패 시 되돌릴 상태입니다. 첫 변경이 일어날 때 붙잡아 둡니다.
    List<Clothes>? previousItems;
    Clothes? previousSelected;
    var mutationVersion = _mutationVersion;

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
        weightSource: current.weightSource,
        calculationScope: current.calculationScope,
        calculationBasis: current.calculationBasis,
        calculationSource: current.calculationSource,
        calculationNote: current.calculationNote,
      );

      if (updatedCount == 0) {
        previousItems = List<Clothes>.from(_items);
        previousSelected = _selectedClothes;
        mutationVersion = ++_mutationVersion;
        _carryFirstSyncUploadPast(mutationVersion);
      }

      _items[index] = updated;

      if (identical(_selectedClothes, current)) {
        _selectedClothes = updated;
      }

      updatedCount++;
    }

    if (updatedCount > 0) {
      notifyListeners();

      try {
        await _persist();
      } catch (_) {
        // 다른 변경 경로(추가·삭제·수정)는 모두 저장 실패 시 되돌리는데 이 경로만
        // 빠져 있었습니다. 되돌리지 않으면 메모리에는 서버 값이, 저장소에는 옛 값이
        // 남아 다음 실행에서 아무 안내 없이 옛 값으로 돌아갑니다.
        final snapshot = previousItems;

        if (mutationVersion == _mutationVersion && snapshot != null) {
          _items
            ..clear()
            ..addAll(snapshot);
          _selectedClothes = previousSelected;
          notifyListeners();
        }

        rethrow;
      }
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
    String ownerKey, {
    required bool migrateLegacyData,
  }) async {
    // 존재 확인과 로드를 한 번의 읽기로 처리해 시작 경로의 저장소 I/O를 줄입니다.
    final (accountItems, accountStatus) = await _storageService
        .loadClothesListWithStatusFor(ownerKey);
    final hasAccountData = accountStatus != ClosetLoadStatus.missing;

    // 계정 옷장 키가 없거나 값이 망가졌으면 서버 백업과 맞춘 상태도 믿을 수 없습니다.
    // 저장보다 먼저 지워, 다음 동기화가 서버 백업을 받아 합치게 합니다(DECISIONS 242).
    if (accountStatus != ClosetLoadStatus.ok) {
      await _storageService.clearClosetBackupStateFor(ownerKey);
    }

    // 예전 공용 옷장은 계정 옷장에 실제로 합쳐 저장한 뒤에만 비워서 유실을 막습니다.
    final legacyItems = migrateLegacyData
        ? await _storageService.loadClothesListOrNull()
        : null;
    final shouldClearLegacyData = legacyItems != null;

    final savedItems = [...accountItems, ...?legacyItems];
    final migratedItems = savedItems
        .where((item) => !_isLegacySampleClothes(item))
        .toList();

    _mutationVersion++;
    _closetOwnerKey = ownerKey;
    _items
      ..clear()
      ..addAll(migratedItems);
    _selectedClothes = _items.isNotEmpty ? _items.last : null;

    if (!hasAccountData ||
        accountStatus == ClosetLoadStatus.corrupt ||
        shouldClearLegacyData ||
        migratedItems.length != savedItems.length) {
      await _storageService.saveClothesListFor(ownerKey, _items);
    }

    if (shouldClearLegacyData) {
      await _storageService.clearClothesList();
    }
  }

  void _clearClosetMemory() {
    _mutationVersion++;
    _items.clear();
    _selectedClothes = null;
    _closetOwnerKey = null;
  }

  /// 이 기기 옷장을 서버 백업과 맞추고, 서버에서 새로 들어온 옷 수를 돌려줍니다(DECISIONS 242).
  ///
  /// 스플래시(세션 유효)와 로그인 뒤 동기화가 [setUserProfile] 바로 뒤에 부릅니다. 이 계정 백업과
  /// 맞춘 적이 없을 때만 서버 백업을 받아 합치고(첫 맞춤), 이미 맞췄으면 바뀐 내용만 올립니다.
  /// 기다리는 것은 받기·합치기·상태 저장까지이고 올리기는 기다리지 않습니다. 예외를 던지지 않습니다.
  Future<int> syncClosetBackup() async {
    final api = _backupApi;
    final ownerKey = _closetOwnerKey;
    final token = _backupToken;
    final userId = _userId;

    if (api == null || ownerKey == null || token == null || userId == null) {
      return 0;
    }
    if (!_firstSyncRunningOwnerKeys.add(ownerKey)) return 0;

    try {
      final state = await _storageService.loadClosetBackupStateFor(ownerKey);
      if (ownerKey != _closetOwnerKey) return 0;

      if (state != null &&
          state.matches(userId: userId, apiBaseUrl: api.baseUrl)) {
        // 켜기만 한 폰은 지문이 같아 올리지 않습니다 — 다른 폰에서 바꾼 백업을 덮지 않게.
        if (closetFingerprint(_items) != state.fingerprint) {
          _scheduleBackupUpload();
        }
        return 0;
      }

      return await _runFirstSync(
        api,
        ownerKey: ownerKey,
        token: token,
        userId: userId,
      );
    } catch (error) {
      // 옷 이름·소재가 로그에 남지 않게 오류의 종류만 적습니다.
      debugPrint('옷장 서버 백업과 맞추지 못했습니다: ${error.runtimeType}');
      return 0;
    } finally {
      _firstSyncRunningOwnerKeys.remove(ownerKey);
    }
  }

  /// 예약된 백업 올리기를 거두고, [scheduleClosetBackup]·로그아웃 전까지 새로 예약하지 않습니다.
  /// 탈퇴 요청 전에 부릅니다 — 올리는 중이던 요청이 끝난 뒤 다시 올리는 것도 막습니다.
  void cancelScheduledClosetBackup() {
    _isBackupPaused = true;
    _cancelBackupTimers();
  }

  /// [cancelScheduledClosetBackup] 으로 거둔 예약을 되돌립니다 — 서버에 닿지 못한 첫 맞춤이 있으면 그것을,
  /// 아니면 올리기를 예약합니다(올리기는 지금 옷장이 맞춘 내용과 다를 때만 보냅니다).
  void scheduleClosetBackup() {
    _isBackupPaused = false;
    final ownerKey = _closetOwnerKey;
    if (ownerKey != null) _onAccountClosetSaved(ownerKey);
  }

  // 첫 맞춤: 서버 백업을 받아, 기기 목록 + 기기에 짝이 없는 서버 옷으로 합치고, 올리기 전에
  // '서버 판을 이 기기 표기로 본 지문'을 상태로 남깁니다.
  //
  // [conflictMutationVersion] 은 첫 올리기가 409 를 받아 한 번 더 받을 때 그 순간의 변경 번호입니다.
  // 이때 기기는 이미 '맞춘 기기'라, 받는 사이 기기가 바뀌었으면 합치지 않고 폰 우선으로 올립니다
  // — 합치면 그사이 지운 옷이 되살아납니다.
  Future<int> _runFirstSync(
    ClosetBackupApi api, {
    required String ownerKey,
    required String token,
    required int userId,
    int? conflictMutationVersion,
  }) async {
    final isRetry = conflictMutationVersion != null;

    if (_isBackupStopped(ownerKey, token)) return 0;

    _lastFirstSyncAttemptAt = _now();
    final result = await api.fetch(accessToken: token);

    final ClosetBackupFetched fetched;
    switch (result) {
      case ClosetBackupFetched():
        fetched = result;
      case ClosetBackupFetchFailed(failure: ClosetBackupFailure.unavailable):
        // 다시 받기는 이미 맞춘 기기라, 다음 변경 때 보통 올리기(409 면 폰 우선)로 이어 갑니다.
        if (!isRetry) _firstSyncRetryOwnerKey = ownerKey;
        return 0;
      case ClosetBackupFetchFailed(:final failure):
        _stopBackup(failure, ownerKey: ownerKey, token: token);
        return 0;
    }

    if (ownerKey != _closetOwnerKey ||
        ownerKey == _purgingOwnerKey ||
        token != _backupToken ||
        fetched.userId != userId) {
      return 0;
    }

    // 서버 옷을 하나라도 못 읽으면 합치지도 올리지도 않습니다 — 읽지 못한 백업을 덮지 않게.
    final serverItems = _parseBackupClothes(fetched.items);
    if (serverItems == null) return 0;

    // 상태는 그대로 둡니다 — 그사이 폰 우선으로 올려 받은 더 새 판을 이 받기의 판으로 되돌리지 않게.
    if (isRetry && conflictMutationVersion != _mutationVersion) {
      _scheduleBackupUpload();
      return 0;
    }

    // 계산과 반영 사이에 await 를 두지 않아, 그 사이 들어온 변경을 잃지 않게 합니다.
    final merged = _mergeWithBackupClothes(_items, serverItems);
    final restoredCount = merged.length - _items.length;

    if (restoredCount > 0) {
      final mutationVersion = ++_mutationVersion;
      final previousItems = List<Clothes>.of(_items);
      final previousSelected = _selectedClothes;

      _items
        ..clear()
        ..addAll(merged);
      _selectedClothes = _items.last;
      _notifyIfAlive();

      try {
        await _storageService.saveClothesListFor(ownerKey, merged);
      } catch (error) {
        if (mutationVersion == _mutationVersion) {
          _items
            ..clear()
            ..addAll(previousItems);
          _selectedClothes = previousSelected;
          _notifyIfAlive();
        }
        debugPrint('서버 백업에서 받은 옷을 저장하지 못했습니다: ${error.runtimeType}');
        return 0;
      }

      // 저장하는 사이 다른 계정으로 바뀌었으면 그 계정 화면에 알리지 않습니다.
      if (!_isDisposed && ownerKey == _closetOwnerKey) {
        _closetRestoreController.add(restoredCount);
      }
    }

    final mutationVersionAfterMerge = _mutationVersion;
    if (ownerKey == _purgingOwnerKey) return restoredCount;

    try {
      // 올리기보다 먼저 남겨, 올리기가 실패해도 이 기기는 '맞춘 기기'가 됩니다.
      // 그래야 다음 실행에서 다시 합쳐 이 기기에서 지운 옷이 돌아오지 않습니다.
      await _storageService.saveClosetBackupStateFor(
        ownerKey,
        ClosetBackupState(
          userId: userId,
          apiBaseUrl: api.baseUrl,
          version: fetched.version,
          fingerprint: closetFingerprint(serverItems),
        ),
      );
    } catch (error) {
      debugPrint('옷장 백업 상태를 저장하지 못했습니다: ${error.runtimeType}');
      return restoredCount;
    }

    if (_firstSyncRetryOwnerKey == ownerKey) _firstSyncRetryOwnerKey = null;

    if (ownerKey == _closetOwnerKey &&
        closetFingerprint(_items) != closetFingerprint(serverItems)) {
      _firstSyncUpload = isRetry
          ? null
          : (ownerKey: ownerKey, mutationVersion: mutationVersionAfterMerge);
      _scheduleBackupUpload();
    }

    return restoredCount;
  }

  // 서버 이력 반영은 사용자가 바꾼 것이 아니라, 첫 맞춤 직후라면 409 때 다시 받아 합치는 보호를 그대로 둡니다.
  // (스플래시·로그인은 첫 맞춤 바로 뒤에 이력을 맞추므로, 세면 다른 폰 옷이 늘 폰 우선 재전송에 덮입니다.)
  void _carryFirstSyncUploadPast(int mutationVersion) {
    final firstSync = _firstSyncUpload;

    if (firstSync != null &&
        firstSync.ownerKey == _closetOwnerKey &&
        firstSync.mutationVersion == mutationVersion - 1) {
      _firstSyncUpload = (
        ownerKey: firstSync.ownerKey,
        mutationVersion: mutationVersion,
      );
    }
  }

  // 옷장이 바뀌어 계정 칸에 저장된 뒤 부릅니다.
  void _onAccountClosetSaved(String ownerKey) {
    if (_backupApi == null) return;

    if (_firstSyncRetryOwnerKey == ownerKey) {
      _scheduleFirstSyncRetry();
      return;
    }

    _scheduleBackupUpload();
  }

  void _scheduleBackupUpload() {
    if (_backupApi == null || _isDisposed || _isBackupPaused) return;

    _backupUploadTimer?.cancel();
    _backupUploadTimer = Timer(backupUploadDelay, () {
      _backupUploadTimer = null;
      unawaited(_runBackupUpload());
    });
  }

  // 서버에 닿지 못한 첫 맞춤을 다시 합니다. 마지막 시도에서 [firstSyncRetryInterval] 은 둡니다.
  void _scheduleFirstSyncRetry() {
    if (_isDisposed || _isBackupPaused) return;

    var delay = backupUploadDelay;
    final lastAttemptAt = _lastFirstSyncAttemptAt;

    if (lastAttemptAt != null) {
      final remaining =
          firstSyncRetryInterval - _now().difference(lastAttemptAt);
      if (remaining > delay) delay = remaining;
    }

    _firstSyncRetryTimer?.cancel();
    _firstSyncRetryTimer = Timer(delay, () {
      _firstSyncRetryTimer = null;
      unawaited(syncClosetBackup());
    });
  }

  void _cancelBackupTimers() {
    // 올리는 중 대기하던 다시 올리기도 거둡니다 — 끝난 뒤 새 타이머가 생기지 않게.
    _isBackupUploadQueued = false;
    _backupUploadTimer?.cancel();
    _backupUploadTimer = null;
    _firstSyncRetryTimer?.cancel();
    _firstSyncRetryTimer = null;
  }

  // 지금 옷장을 서버에 올립니다. 동시에 하나만 보내고, 보낼 값은 보내는 순간 한 번에 잡습니다.
  Future<void> _runBackupUpload() async {
    final api = _backupApi;
    if (api == null || _isDisposed) return;

    if (_isBackupUploading) {
      _isBackupUploadQueued = true;
      return;
    }

    final ownerKey = _closetOwnerKey;
    final token = _backupToken;
    final userId = _userId;

    if (ownerKey == null || token == null || userId == null) return;
    if (_isBackupStopped(ownerKey, token)) return;

    _isBackupUploading = true;
    var retryFirstSync = false;
    int? firstSyncMutationVersionAtConflict;

    try {
      final state = await _storageService.loadClosetBackupStateFor(ownerKey);

      // 상태를 읽는 사이 계정이 바뀌었으면 보내지 않습니다.
      if (ownerKey != _closetOwnerKey ||
          token != _backupToken ||
          userId != _userId) {
        return;
      }
      if (state == null ||
          !state.matches(userId: userId, apiBaseUrl: api.baseUrl)) {
        return;
      }

      final snapshot = List<Clothes>.of(_items);
      final sentFingerprint = closetFingerprint(snapshot);
      if (sentFingerprint == state.fingerprint) return;

      final payload = snapshot.map((item) => item.toJson()).toList();
      final firstSync = _firstSyncUpload;
      _firstSyncUpload = null;
      final firstSyncMutationVersion = firstSync?.ownerKey == ownerKey
          ? firstSync?.mutationVersion
          : null;

      var result = await api.upload(
        accessToken: token,
        userId: userId,
        baseVersion: state.version,
        items: payload,
      );

      if (result is ClosetBackupConflict) {
        final isSameSession =
            ownerKey == _closetOwnerKey && token == _backupToken;

        if (isSameSession && firstSyncMutationVersion == _mutationVersion) {
          // 첫 맞춤 뒤 이 기기는 그대로인데 다른 기기가 먼저 바꿨으면, 덮지 않고 한 번 더 받아 합칩니다.
          retryFirstSync = true;
          firstSyncMutationVersionAtConflict = _mutationVersion;
          return;
        }

        if (!isSameSession) return;

        // 폰 우선: 같은 목록을 지금 서버 판 위에 한 번 더 보냅니다. 또 409 면 다음 변경 때.
        result = await api.upload(
          accessToken: token,
          userId: userId,
          baseVersion: result.currentVersion,
          items: payload,
        );
      }

      switch (result) {
        case ClosetBackupUploaded(:final version):
          // 보낼 때 잡아 둔 주인의 상태에 씁니다(그사이 주인이 바뀌었어도).
          await _storageService.saveClosetBackupStateFor(
            ownerKey,
            ClosetBackupState(
              userId: userId,
              apiBaseUrl: api.baseUrl,
              version: version,
              fingerprint: sentFingerprint,
            ),
          );
          if (ownerKey == _closetOwnerKey &&
              closetFingerprint(_items) != sentFingerprint) {
            _isBackupUploadQueued = true;
          }
        case ClosetBackupConflict():
          break;
        case ClosetBackupUploadFailed(:final failure):
          _stopBackup(failure, ownerKey: ownerKey, token: token);
      }
    } catch (error) {
      debugPrint('옷장 서버 백업을 올리지 못했습니다: ${error.runtimeType}');
    } finally {
      _isBackupUploading = false;

      if (retryFirstSync && !_isBackupPaused) {
        unawaited(
          _retryFirstSyncAfterConflict(
            api,
            ownerKey,
            token,
            userId,
            conflictMutationVersion: firstSyncMutationVersionAtConflict!,
          ),
        );
      } else if (_isBackupUploadQueued) {
        _isBackupUploadQueued = false;
        _scheduleBackupUpload();
      }
    }
  }

  Future<void> _retryFirstSyncAfterConflict(
    ClosetBackupApi api,
    String ownerKey,
    String token,
    int userId, {
    required int conflictMutationVersion,
  }) async {
    if (_isDisposed || !_firstSyncRunningOwnerKeys.add(ownerKey)) return;

    try {
      await _runFirstSync(
        api,
        ownerKey: ownerKey,
        token: token,
        userId: userId,
        conflictMutationVersion: conflictMutationVersion,
      );
    } catch (error) {
      debugPrint('옷장 서버 백업과 다시 맞추지 못했습니다: ${error.runtimeType}');
    } finally {
      _firstSyncRunningOwnerKeys.remove(ownerKey);
    }
  }

  // 401 은 그 토큰으로, 거절은 그 옷장 주인으로 이번 실행 동안 멈춥니다. 403 주인 불일치와
  // 못 닿음은 이번 시도만 버립니다.
  void _stopBackup(
    ClosetBackupFailure failure, {
    required String ownerKey,
    required String token,
  }) {
    switch (failure) {
      case ClosetBackupFailure.unauthorized:
        _backupUnauthorizedTokens.add(token);
      case ClosetBackupFailure.rejected:
        _backupRejectedOwnerKeys.add(ownerKey);
        debugPrint('서버가 옷장 백업을 거절해 이번 실행 동안 멈춥니다.');
      case ClosetBackupFailure.ownerMismatch:
      case ClosetBackupFailure.unavailable:
        break;
    }
  }

  bool _isBackupStopped(String ownerKey, String token) {
    return _backupRejectedOwnerKeys.contains(ownerKey) ||
        _backupUnauthorizedTokens.contains(token);
  }

  // 만료된 세션의 토큰으로는 백업을 부르지 않습니다.
  String? get _backupToken =>
      isAuthenticated ? _authSession!.accessToken : null;

  void _notifyIfAlive() {
    if (!_isDisposed) notifyListeners();
  }

  // 서버 백업의 원소를 모두 옷으로 읽습니다. 하나라도 못 읽으면 null 입니다.
  static List<Clothes>? _parseBackupClothes(List<Object?> rawItems) {
    final items = <Clothes>[];

    for (final rawItem in rawItems) {
      if (rawItem is! Map) return null;

      try {
        items.add(Clothes.fromJson(Map<String, dynamic>.from(rawItem)));
      } catch (_) {
        return null;
      }
    }

    return items;
  }

  /// 첫 맞춤 합치기: 기기 목록(순서·내용 그대로) + 기기에 짝이 없는 서버 옷(서버 순서)입니다.
  ///
  /// 짝은 등록 시각이 둘 다 있으면 그 글자와 서버 저장 id 가 모두 같을 때, 둘 다 없으면 저장
  /// 글자 전체가 같을 때이고, 한쪽만 있으면 짝이 아닙니다. 한 벌은 한 번만 짝이 됩니다.
  static List<Clothes> _mergeWithBackupClothes(
    List<Clothes> localItems,
    List<Clothes> serverItems,
  ) {
    final unmatchedLocal = <String, int>{};

    for (final item in localItems) {
      final key = _backupMatchKey(item);
      unmatchedLocal[key] = (unmatchedLocal[key] ?? 0) + 1;
    }

    final merged = List<Clothes>.of(localItems);

    for (final item in serverItems) {
      final key = _backupMatchKey(item);
      final remaining = unmatchedLocal[key] ?? 0;

      if (remaining > 0) {
        unmatchedLocal[key] = remaining - 1;
      } else {
        merged.add(item);
      }
    }

    return merged;
  }

  // 같은 키 = 짝입니다. 등록 시각이 있는 옷('r:')과 없는 옷('j:')은 키가 겹치지 않습니다.
  static String _backupMatchKey(Clothes item) {
    final json = item.toJson();
    final registeredAt = json['registeredAt'];

    if (registeredAt != null) {
      return 'r:$registeredAt|${item.savedResultId}';
    }
    return 'j:${jsonEncode(json)}';
  }

  /// 계정별 옷장의 주인 키입니다. 이메일 계정은 지금까지처럼 정규화한 이메일을 써서 이미 저장된
  /// 옷장 키가 바뀌지 않게 하고, 이메일이 없는 계정(카카오)은 서버 사용자 id 로 `user:<id>` 를
  /// 씁니다. 이메일에는 늘 `@` 가 있어 두 키가 겹치지 않습니다. id 는 서버마다 따로라, 개발 중
  /// 한 기기에서 서버를 바꾸면 다른 서버의 같은 id 와 키가 같아집니다(배포 앱은 서버 하나).
  static String? _closetOwnerKeyFor({String? email, int? userId}) {
    final normalizedEmail = email?.trim().toLowerCase() ?? '';

    if (normalizedEmail.isNotEmpty) return normalizedEmail;
    return userId == null ? null : 'user:$userId';
  }

  static List<String> _defaultLoginMethods(String? email) {
    return email == null ? const [] : const [LoginMethod.password];
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
    // 방어적 복사: newOrder가 items 게터(살아 있는 UnmodifiableListView)이면
    // clear() 시점에 원본도 함께 비어 addAll이 아무것도 넣지 못한다.
    final order = List<Clothes>.of(newOrder);
    final mutationVersion = ++_mutationVersion;
    final previousOrder = List<Clothes>.from(_items);
    final previousSelected = _selectedClothes;

    _items
      ..clear()
      ..addAll(order);

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

    final ownerKey = _closetOwnerKey;
    if (ownerKey == null) {
      await _storageService.clearClothesList();
      return;
    }

    await _storageService.clearClothesListFor(ownerKey);
  }

  @override
  void dispose() {
    _isDisposed = true;
    _cancelBackupTimers();
    _closetRestoreController.close();
    super.dispose();
  }
}
