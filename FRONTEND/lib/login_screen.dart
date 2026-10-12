// 로그인과 회원가입 진입점을 제공하는 인증 시작 화면입니다. 카카오 로그인은 이 화면에서 끝까지
// 처리합니다(DECISIONS 140·183).
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'config/kakao_config.dart';
import 'kakao_nickname_screen.dart';
import 'services/auth_api_service.dart';
import 'services/kakao_login_service.dart';
import 'services/post_login_sync_service.dart';
import 'theme/app_palette.dart';
import 'widgets/app_banner.dart';
import 'widgets/auth_form_widgets.dart';
import 'widgets/kakao_login_button.dart';
import 'widgets/kdpp_logo_mark.dart';

/// 서비스 소개와 함께 카카오 로그인, 이메일 로그인·회원가입 화면으로 이동하는 버튼을 표시합니다.
///
/// 카카오 버튼은 맨 위, 그 아래 '이메일로 로그인'과 회원가입 링크를 붙여 둡니다 — 카카오 버튼이
/// 사이에 끼면 회원가입 링크가 카카오 가입처럼 보입니다(DECISIONS 183 ①).
class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    this.authApiService,
    this.kakaoLoginService,
    this.showKakaoLogin,
  });

  final AuthApiService? authApiService;
  final KakaoLoginService? kakaoLoginService;

  /// 카카오 로그인 버튼을 보일지입니다. 비우면 카카오 키가 있는 빌드에서만 보입니다([KakaoConfig]).
  final bool? showKakaoLogin;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late final AuthApiService _authApiService;
  late final KakaoLoginService _kakaoLoginService;
  late final PostLoginSyncService _postLoginSyncService;

  /// 카카오 로그인이 진행 중인지입니다. 그동안은 이 화면의 버튼을 모두 막습니다.
  bool _isKakaoLoading = false;

  @override
  void initState() {
    super.initState();
    _authApiService = widget.authApiService ?? AuthApiService();
    _kakaoLoginService = widget.kakaoLoginService ?? KakaoLoginService();
    _postLoginSyncService = PostLoginSyncService(
      authApiService: _authApiService,
    );
  }

  /// 카카오 SDK 로그인 → 서버 로그인(필요하면 닉네임) → 세션 저장 → 서버 이력 동기화 → 메인.
  Future<void> _signInWithKakao() async {
    if (_isKakaoLoading) return;

    setState(() => _isKakaoLoading = true);

    try {
      final kakaoAccessToken = await _kakaoLoginService.signIn();

      // 카카오 화면에서 취소하면 서버를 부르지 않는다.
      if (kakaoAccessToken == null || !mounted) return;

      final result = await _requestKakaoLogin(kakaoAccessToken);

      if (result == null || !mounted) return;

      await _completeSignIn(result);
    } on KakaoLoginException catch (error) {
      debugPrint('카카오 로그인을 마치지 못했습니다: ${error.cause}');

      if (!mounted) return;

      AppBanner.of(
        context,
      ).show(error.userMessage, kind: AppBannerKind.failure);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      // 로그인 API 의 401 은 세션 만료가 아니라 카카오 토큰 거부라 이 화면에서 안내한다.
      AppBanner.of(
        context,
      ).show(error.userMessage, kind: AppBannerKind.failure);
    } catch (error, stackTrace) {
      debugPrint('카카오 로그인 세션 저장 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) return;

      AppBanner.of(context).show(
        '로그인 정보를 안전하게 저장하지 못했어요. 다시 시도해 주세요.',
        kind: AppBannerKind.failure,
      );
    } finally {
      if (mounted) {
        setState(() => _isKakaoLoading = false);
      }
    }
  }

  /// 카카오 토큰만 먼저 보내고(DECISIONS 163), 서버가 닉네임을 요구하면 닉네임 화면에서 받아
  /// 같은 토큰으로 다시 보낸다. 닉네임 화면에서 그냥 돌아오면 null 이다.
  Future<AuthResult?> _requestKakaoLogin(String kakaoAccessToken) async {
    try {
      return await _authApiService.kakaoLogin(accessToken: kakaoAccessToken);
    } on AuthApiException catch (error) {
      if (error.errorCode != AuthErrorCode.socialNicknameRequired) rethrow;
    }

    if (!mounted) return null;

    return Navigator.push<AuthResult>(
      context,
      MaterialPageRoute(
        builder: (_) => KakaoNicknameScreen(
          authApiService: _authApiService,
          kakaoAccessToken: kakaoAccessToken,
        ),
      ),
    );
  }

  /// 이메일 로그인(`email_login_screen.dart`)과 같은 순서로 로그인을 마친다.
  Future<void> _completeSignIn(AuthResult result) async {
    final provider = context.read<ClosetProvider>();
    final accessToken = result.accessToken!;

    await provider.setAuthenticatedUser(
      nickname: result.user.nickname,
      email: result.user.email,
      userId: result.user.id,
      loginMethods: result.user.loginMethods,
      accessToken: accessToken,
      expiresInSeconds: result.expiresInSeconds!,
    );

    if (!mounted) return;

    await _postLoginSyncService.synchronize(
      provider: provider,
      accessToken: accessToken,
    );

    if (!mounted) return;

    Navigator.pushNamedAndRemoveUntil(context, '/main', (route) => false);

    // 이메일 계정과 자동으로 합치지 않으므로(DECISIONS 143) 새 계정이 생겼음을 알린다.
    if (result.isNewUser) {
      AppBanner.of(
        context,
      ).show('카카오 계정으로 가입했어요.', kind: AppBannerKind.success);
    }
  }

  @override
  Widget build(BuildContext context) {
    final showKakaoLogin = widget.showKakaoLogin ?? KakaoConfig.isEnabled;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final backgroundColor = palette.background;
    final primaryText = isDark ? Colors.white : const Color(0xFF1A1A1A);
    final secondaryText = palette.textSecondary;

    return Scaffold(
      backgroundColor: backgroundColor,
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: IntrinsicHeight(
                  child: Column(
                    children: [
                      const Spacer(flex: 2),
                      const KdppLogoMark(size: 96, semanticLabel: null),
                      const SizedBox(height: 24),
                      Text(
                        'K-DPP',
                        style: TextStyle(
                          fontSize: 30,
                          fontWeight: FontWeight.bold,
                          color: primaryText,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        '의류를 더 오래, 더 바르게 관리하세요',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 16,
                          color: secondaryText,
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '라벨 스캔으로 의류 상태와 관리 정보를\n쉽게 확인할 수 있어요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 14,
                          color: secondaryText,
                          height: 1.5,
                        ),
                      ),
                      const Spacer(flex: 3),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 28),
                        child: Column(
                          children: [
                            if (showKakaoLogin) ...[
                              KakaoLoginButton(
                                isLoading: _isKakaoLoading,
                                onPressed: _signInWithKakao,
                              ),
                              const SizedBox(height: 12),
                            ],
                            SizedBox(
                              width: double.infinity,
                              height: 56,
                              child: ElevatedButton(
                                // 카카오 로그인 중에 다른 화면으로 가면, 끝난 로그인이 그 화면을
                                // 메인으로 바꿔 버린다.
                                onPressed: _isKakaoLoading
                                    ? null
                                    : () {
                                        Navigator.pushNamed(
                                          context,
                                          '/email-login',
                                        );
                                      },
                                style: ElevatedButton.styleFrom(
                                  elevation: 0,
                                  backgroundColor: AppPalette.accent,
                                  disabledBackgroundColor: const Color(
                                    0x8C4A4EFE,
                                  ),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                ),
                                // 카카오 버튼과 나란하면 '로그인'만으로는 어느 쪽인지 모른다.
                                child: const Text(
                                  '이메일로 로그인',
                                  style: TextStyle(
                                    fontSize: 16,
                                    color: Colors.white,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(height: 10),
                            AuthLinkButton(
                              prompt: '계정이 없으신가요?',
                              action: '회원가입',
                              onPressed: _isKakaoLoading
                                  ? null
                                  : () {
                                      Navigator.pushNamed(context, '/signup');
                                    },
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}
