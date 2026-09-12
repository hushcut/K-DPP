import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/closet_provider.dart';
import 'package:k_dpp/services/auth_api_service.dart';
import 'package:k_dpp/services/auth_session_storage_service.dart';
import 'package:k_dpp/services/auth_session_validation_service.dart';
import 'package:k_dpp/services/closet_storage_service.dart';
import 'package:k_dpp/splash_screen.dart';
import 'package:provider/provider.dart';

import 'helpers/fake_auth_session_storage.dart';
import 'helpers/fake_closet_storage.dart';

void main() {
  testWidgets('인증 저장소 오류가 발생하면 로그인 화면으로 안전하게 이동한다', (tester) async {
    final originalDebugPrint = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {};

    final authStorage = FakeAuthSessionStorage()
      ..loadError = StateError('secure storage unavailable');
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) =>
                const SplashScreen(minimumDisplayDuration: Duration.zero),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('로그인 화면'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);
    debugPrint = originalDebugPrint;
  });

  testWidgets('유효한 저장 세션은 서버 검증 후 메인 화면으로 이동한다', (tester) async {
    final authStorage = FakeAuthSessionStorage()
      ..savedSession = AuthSession(
        accessToken: 'valid-token',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) => SplashScreen(
              minimumDisplayDuration: Duration.zero,
              authSessionValidationService: _FakeValidationService(
                const AuthSessionValid(
                  AuthUser(
                    id: 1,
                    email: 'honggildong@example.com',
                    nickname: '홍길동',
                  ),
                ),
              ),
            ),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('메인 화면'), findsOneWidget);
    expect(find.text('로그인 화면'), findsNothing);
    expect(provider.userName, '홍길동');
    expect(provider.userEmail, 'honggildong@example.com');
  });

  // C33: 세션 검증의 세 분기(Invalid / Unavailable / 프로필 동기화 실패) 중
  // 여태 테스트된 것은 없다(위 두 테스트는 저장소 오류·Valid 성공만 다룬다).
  testWidgets('서버가 인증을 거부하면(Invalid) 로그인 화면으로 보내고 저장 세션을 지운다', (
    tester,
  ) async {
    final authStorage = FakeAuthSessionStorage()
      ..savedSession = AuthSession(
        accessToken: 'stale-token',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) => SplashScreen(
              minimumDisplayDuration: Duration.zero,
              authSessionValidationService: _FakeValidationService(
                const AuthSessionInvalid(),
              ),
            ),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('로그인 화면'), findsOneWidget);
    expect(find.text('메인 화면'), findsNothing);
    expect(provider.isAuthenticated, isFalse);
    expect(authStorage.savedSession, isNull);
  });

  testWidgets('서버 확인이 안 되면(Unavailable) 로컬 세션을 유지한 채 메인 화면으로 보낸다', (
    tester,
  ) async {
    final authStorage = FakeAuthSessionStorage()
      ..savedSession = AuthSession(
        accessToken: 'valid-token',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) => SplashScreen(
              minimumDisplayDuration: Duration.zero,
              authSessionValidationService: _FakeValidationService(
                const AuthSessionUnavailable(
                  AuthApiException(
                    type: AuthApiErrorType.network,
                    message: '네트워크 오류',
                  ),
                ),
              ),
            ),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('메인 화면'), findsOneWidget);
    expect(find.text('로그인 화면'), findsNothing);
    expect(provider.isAuthenticated, isTrue);
    expect(provider.accessToken, 'valid-token');
  });

  testWidgets('Valid 세션이어도 프로필·이력 동기화가 실패하면 예외를 삼키고 메인 화면으로 보낸다', (
    tester,
  ) async {
    final originalDebugPrint = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {};

    final authStorage = FakeAuthSessionStorage()
      ..savedSession = AuthSession(
        accessToken: 'valid-token',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final provider = _ThrowingProfileClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider<ClosetProvider>.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) => SplashScreen(
              minimumDisplayDuration: Duration.zero,
              authSessionValidationService: _FakeValidationService(
                const AuthSessionValid(
                  AuthUser(
                    id: 1,
                    email: 'honggildong@example.com',
                    nickname: '홍길동',
                  ),
                ),
              ),
            ),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('메인 화면'), findsOneWidget);
    expect(find.text('로그인 화면'), findsNothing);
    expect(provider.isAuthenticated, isTrue);
    debugPrint = originalDebugPrint;
  });

  // 프론트 백로그 7c: 최소 표시 시간이 초기화와 병렬로 도는지는 여태 테스트가 없었다.
  // 위 테스트들은 minimumDisplayDuration이 Duration.zero라 순차 회귀를 잡지 못한다.
  testWidgets('최소 표시 시간은 초기화와 병렬로 진행돼 두 시간이 합산되지 않는다', (tester) async {
    final authStorage = FakeAuthSessionStorage()
      ..savedSession = AuthSession(
        accessToken: 'valid-token',
        expiresAt: DateTime.now().add(const Duration(hours: 1)),
      );
    final provider = ClosetProvider(
      storage: FakeClosetStorage(),
      authSessionStorage: authStorage,
    );

    await tester.pumpWidget(
      ChangeNotifierProvider.value(
        value: provider,
        child: MaterialApp(
          initialRoute: '/splash',
          routes: {
            '/splash': (context) => SplashScreen(
              minimumDisplayDuration: const Duration(milliseconds: 2000),
              authSessionValidationService: _DelayedValidationService(
                const AuthSessionValid(
                  AuthUser(
                    id: 1,
                    email: 'honggildong@example.com',
                    nickname: '홍길동',
                  ),
                ),
                const Duration(milliseconds: 1500),
              ),
            ),
            '/login': (context) => const Scaffold(body: Text('로그인 화면')),
            '/main': (context) => const Scaffold(body: Text('메인 화면')),
          },
        ),
      ),
    );

    // 초기화(1500ms)가 최소 표시(2000ms)보다 먼저 끝나도, 병렬이면 이동 시각은
    // max(2000, 1500) = 2000ms 근처다. 순차로 되돌리면 3500ms가 걸려
    // 1900ms는 물론 2100ms에도 아직 이동하지 않는다.
    for (var elapsed = 0; elapsed < 1900; elapsed += 25) {
      await tester.pump(const Duration(milliseconds: 25));
    }
    expect(find.text('메인 화면'), findsNothing);
    expect(find.text('로그인 화면'), findsNothing);

    for (var elapsed = 1900; elapsed < 2100; elapsed += 25) {
      await tester.pump(const Duration(milliseconds: 25));
    }
    expect(find.text('메인 화면'), findsOneWidget);

    await tester.pumpAndSettle();
  });
}

class _FakeValidationService extends AuthSessionValidationService {
  _FakeValidationService(this.result);

  final AuthSessionValidationResult result;

  @override
  Future<AuthSessionValidationResult> validate({
    required String accessToken,
  }) async {
    return result;
  }
}

/// 초기화(서버 검증)가 끝나는 시점을 제어해 최소 표시 시간과의 병렬 진행을
/// 테스트할 수 있게 하는 가짜 검증 서비스입니다.
class _DelayedValidationService extends AuthSessionValidationService {
  _DelayedValidationService(this.result, this.delay);

  final AuthSessionValidationResult result;
  final Duration delay;

  @override
  Future<AuthSessionValidationResult> validate({
    required String accessToken,
  }) async {
    await Future<void>.delayed(delay);
    return result;
  }
}

/// setUserProfile만 실패하는 상황(예: 저장소 오류)을 흉내 내
/// 프로필·이력 동기화 실패가 유효한 로그인 상태를 되돌리지 않는지 확인합니다.
class _ThrowingProfileClosetProvider extends ClosetProvider {
  _ThrowingProfileClosetProvider({
    required ClosetStorage storage,
    required AuthSessionStorage authSessionStorage,
  }) : super(storage: storage, authSessionStorage: authSessionStorage);

  @override
  Future<void> setUserProfile({
    required String nickname,
    required String email,
  }) async {
    throw StateError('setUserProfile 강제 실패 (테스트)');
  }
}
