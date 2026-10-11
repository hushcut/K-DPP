// 이메일·비밀번호 입력을 검증하고 서버 로그인 및 로그인 후 동기화를 수행하는 화면입니다.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'closet_provider.dart';
import 'services/auth_api_service.dart';
import 'services/post_login_sync_service.dart';
import 'signup_screen.dart';
import 'theme/app_palette.dart';
import 'utils/auth_form_validators.dart';
import 'widgets/app_back_button.dart';
import 'widgets/app_banner.dart';
import 'widgets/auth_form_widgets.dart';

/// 로그인 요청의 진행 상태와 비밀번호 표시 상태를 관리하는 이메일 로그인 화면입니다.
class EmailLoginScreen extends StatefulWidget {
  const EmailLoginScreen({super.key, this.authApiService});

  final AuthApiService? authApiService;

  @override
  State<EmailLoginScreen> createState() => _EmailLoginScreenState();
}

class _EmailLoginScreenState extends State<EmailLoginScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  late final AuthApiService _authApiService;
  late final PostLoginSyncService _postLoginSyncService;

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _didLoadInitialEmail = false;

  @override
  void initState() {
    super.initState();
    _authApiService = widget.authApiService ?? AuthApiService();
    _postLoginSyncService = PostLoginSyncService(
      authApiService: _authApiService,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    if (_didLoadInitialEmail) return;
    _didLoadInitialEmail = true;

    // 회원가입 직후 전달된 이메일이 있으면 로그인 폼에 한 번만 채웁니다.
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is String && args.trim().isNotEmpty) {
      _emailController.text = args.trim();
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  // 제출 전에 네트워크 요청 없이 기본 입력 형식을 검사합니다(이메일은 [validateEmailInput]).
  String? _validatePassword(String? value) {
    final text = value?.trim() ?? '';

    if (text.isEmpty) {
      return '비밀번호를 입력해 주세요';
    }

    if (text.length < 8) {
      return '비밀번호는 8자 이상 입력해 주세요';
    }

    return null;
  }

  /// 폼 검증 → 서버 로그인 → 세션 저장 → 서버 이력 동기화 순으로 처리합니다.
  Future<void> _handleLogin() async {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    setState(() {
      _isLoading = true;
    });

    try {
      final result = await _authApiService.login(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );

      if (!mounted) return;

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

      // 인증 화면으로 돌아오지 않도록 이전 경로를 모두 제거합니다.
      Navigator.pushNamedAndRemoveUntil(context, '/main', (route) => false);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      AppBanner.of(context).show(error.userMessage, kind: AppBannerKind.failure);
    } catch (error, stackTrace) {
      debugPrint('로그인 세션 저장 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) return;

      AppBanner.of(context).show(
        '로그인 정보를 안전하게 저장하지 못했어요. 다시 시도해 주세요.',
        kind: AppBannerKind.failure,
      );
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  /// 비밀번호 찾기로 갔다가 재설정에 성공해 돌아오면 그 이메일을 채우고 옛 비밀번호를 지웁니다.
  Future<void> _openPasswordReset() async {
    final result = await Navigator.pushNamed(
      context,
      '/password-reset',
      arguments: _emailController.text.trim(),
    );

    if (!mounted || result is! String || result.trim().isEmpty) return;

    _emailController.text = result.trim();
    _passwordController.clear();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final backgroundColor = palette.background;
    final primaryText = palette.textPrimary;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);
    final iconColor = isDark
        ? const Color(0xFFB8B8BE)
        : const Color(0xFF8C8C8C);

    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        automaticallyImplyLeading: false,
        leadingWidth: 52,
        leading: const Padding(
          padding: EdgeInsets.only(left: 8),
          child: AppBackButton(),
        ),
        title: Text(
          '로그인',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: LayoutBuilder(
            builder: (context, constraints) {
              return SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: ConstrainedBox(
                  // 아래 인셋(자판 등)이 앱바 아래를 다 덮으면 maxHeight 가 0 이 되므로
                  // 빼고 남은 값이 음수가 되지 않게 0 에서 멈춥니다.
                  constraints: BoxConstraints(
                    minHeight: math.max(0.0, constraints.maxHeight - 12),
                  ),
                  child: IntrinsicHeight(
                    child: Column(
                      children: [
                        const SizedBox(height: 48),
                        Text(
                          'K-DPP에 로그인하세요',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: primaryText,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Text(
                          '계정 정보를 입력하고 서비스를 시작해 보세요.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 14,
                            color: secondaryText,
                            height: 1.5,
                          ),
                        ),
                        const SizedBox(height: 40),
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [
                            AutofillHints.username,
                            AutofillHints.email,
                          ],
                          autocorrect: false,
                          validator: validateEmailInput,
                          style: TextStyle(color: primaryText),
                          cursorColor: AppPalette.accent,
                          decoration: authInputDecoration(
                            context,
                            labelText: '이메일',
                            hintText: 'honggildong@example.com',
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _passwordController,
                          obscureText: _obscurePassword,
                          textInputAction: TextInputAction.done,
                          autofillHints: const [AutofillHints.password],
                          enableSuggestions: false,
                          autocorrect: false,
                          validator: _validatePassword,
                          style: TextStyle(color: primaryText),
                          cursorColor: AppPalette.accent,
                          decoration: authInputDecoration(
                            context,
                            labelText: '비밀번호',
                            hintText: '8자 이상 입력',
                            suffixIcon: IconButton(
                              onPressed: () {
                                setState(() {
                                  _obscurePassword = !_obscurePassword;
                                });
                              },
                              tooltip: _obscurePassword
                                  ? '비밀번호 표시'
                                  : '비밀번호 숨기기',
                              icon: Icon(
                                _obscurePassword
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined,
                                color: iconColor,
                              ),
                            ),
                          ),
                          onFieldSubmitted: (_) {
                            if (!_isLoading) {
                              _handleLogin();
                            }
                          },
                        ),
                        const SizedBox(height: 32),
                        AuthSubmitButton(
                          label: '로그인',
                          loadingSemanticsLabel: '로그인 처리 중',
                          isLoading: _isLoading,
                          onPressed: _handleLogin,
                        ),
                        const SizedBox(height: 18),
                        AuthLinkButton(
                          action: '비밀번호를 잊으셨나요?',
                          onPressed: _openPasswordReset,
                        ),
                        const SizedBox(height: 4),
                        AuthLinkButton(
                          prompt: '계정이 없으신가요?',
                          action: '회원가입',
                          onPressed: () async {
                            // 회원가입이 pop으로 돌아오면 이 화면을 재사용하고,
                            // 전달된 이메일이 있으면 로그인 폼에 채웁니다.
                            final result = await Navigator.pushNamed(
                              context,
                              '/signup',
                              arguments: SignupScreen.fromEmailLoginArgument,
                            );

                            if (!mounted ||
                                result is! String ||
                                result.trim().isEmpty) {
                              return;
                            }

                            _emailController.text = result.trim();
                          },
                        ),
                        const Spacer(),
                        const SizedBox(height: 24),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}
