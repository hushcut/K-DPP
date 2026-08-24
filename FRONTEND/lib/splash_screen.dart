// 앱 시작 애니메이션을 보여 주며 저장 데이터와 로그인 세션을 복원하는 화면입니다.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'services/auth_session_validation_service.dart';
import 'widgets/kdpp_logo_mark.dart';

/// 초기화 결과에 따라 메인 화면 또는 로그인 화면으로 사용자를 안내합니다.
class SplashScreen extends StatefulWidget {
  const SplashScreen({
    super.key,
    this.authSessionValidationService,
    this.minimumDisplayDuration = const Duration(milliseconds: 1200),
  });

  final AuthSessionValidationService? authSessionValidationService;
  final Duration minimumDisplayDuration;

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _fadeAnimation;
  late final Animation<double> _scaleAnimation;
  late final AuthSessionValidationService _authSessionValidationService;

  @override
  void initState() {
    super.initState();

    _authSessionValidationService =
        widget.authSessionValidationService ?? AuthSessionValidationService();

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );

    _fadeAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    );

    _scaleAnimation = Tween<double>(
      begin: 0.96,
      end: 1.0,
    ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic));

    // 로고 애니메이션과 앱 초기화는 함께 시작해 대기 시간을 줄입니다.
    _controller.forward();
    _initializeApp();
  }

  /// 로컬 세션을 복원하고 서버 검증 결과에 맞춰 프로필·이력을 동기화합니다.
  Future<void> _initializeApp() async {
    final provider = context.read<ClosetProvider>();
    var shouldOpenMain = false;

    try {
      await provider.loadFromStorage();

      final accessToken = provider.accessToken;

      if (provider.isAuthenticated && accessToken != null) {
        final validation = await _authSessionValidationService.validate(
          accessToken: accessToken,
        );

        // 유효하면 최신 서버 정보를 반영하고, 서버가 인증을 거부한 경우만 로컬 로그아웃 처리합니다.
        switch (validation) {
          case AuthSessionValid(:final user, :final history):
            try {
              await provider.setUserProfile(
                nickname: user.nickname,
                email: user.email,
              );
              await provider.synchronizeServerHistory(history);
            } catch (error, stackTrace) {
              // 프로필·이력 동기화 실패가 유효한 로그인 상태를
              // 로그인 화면으로 되돌리는 원인이 되지 않게 합니다.
              debugPrint('로그인 후 동기화에 실패했습니다: $error');
              debugPrintStack(stackTrace: stackTrace);
            }
          case AuthSessionInvalid():
            await provider.logout();
          case AuthSessionUnavailable():
            break;
        }
      }

      shouldOpenMain = provider.isAuthenticated;
    } catch (error, stackTrace) {
      debugPrint('앱 초기화 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    await Future.delayed(widget.minimumDisplayDuration);

    if (!mounted) return;

    // 초기 화면이 뒤로 가기 스택에 남지 않도록 현재 경로를 교체합니다.
    Navigator.pushReplacementNamed(
      context,
      shouldOpenMain ? '/main' : '/login',
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);

    return Scaffold(
      backgroundColor: backgroundColor,
      body: Center(
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: ScaleTransition(
            scale: _scaleAnimation,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const KdppLogoMark(size: 84, borderRadius: 24),
                const SizedBox(height: 20),
                Text(
                  'K-DPP',
                  style: TextStyle(
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    color: primaryText,
                    letterSpacing: -0.5,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
