package com.cnpm.backend.controller;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import com.cnpm.backend.entity.User;
import com.cnpm.backend.repository.UserRepository;
import com.cnpm.backend.repository.RoleRepository;
import com.cnpm.backend.repository.WorkspaceRepository;
import com.cnpm.backend.repository.WorkspaceMembershipRepository;
import com.cnpm.backend.security.ApiRoutePermissions;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.LinkedHashSet;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/** Proxies authenticated browser requests to GitHub Integration. */
@RestController
@RequestMapping(path = {
        "/api/github/**", "/api/workspaces/**", "/api/repositories/**", "/api/documentation/**",
        "/api/document-workflows/**", "/api/oversight/**", "/api/approval/**"
}, method = {org.springframework.web.bind.annotation.RequestMethod.GET,
        org.springframework.web.bind.annotation.RequestMethod.POST,
        org.springframework.web.bind.annotation.RequestMethod.PUT,
        org.springframework.web.bind.annotation.RequestMethod.DELETE})
public class GitHubIntegrationBffController {

    private static final Pattern WORKSPACE_REPOSITORY_ROUTE =
            Pattern.compile("^/api/workspaces/([^/]+)/repositories(?:/([^/]+))?$");
    private static final Pattern WORKSPACE_COLLECTION_ROUTE =
            Pattern.compile("^/api/workspaces/([^/]+)/collections(?:/.*)?$");
    private static final Pattern DOCUMENT_OWNER_ROUTE =
            Pattern.compile("^/api/workspaces/([^/]+)/collections/[^/]+/documents/[^/]+/owner/([^/]+)$");
    private static final Pattern REPOSITORY_ID_ROUTE =
            Pattern.compile("^/api/repositories/([0-9a-fA-F-]{36})(?:/.*)?$");
    private static final List<String> FORWARDED_RESPONSE_HEADERS = List.of("Retry-After");

    private final RestClient integrationClient;
    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private WorkspaceRepository workspaceRepository;
    private WorkspaceMembershipRepository workspaceMembershipRepository;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final String integrationSecret;
    private final String integrationBaseUrl;

    @Autowired
    public GitHubIntegrationBffController(RestClient.Builder builder,
            UserRepository userRepository,
            RoleRepository roleRepository,
            @Value("${services.github-integration.base-url:http://localhost:8082}") String integrationBaseUrl,
            @Value("${services.github-integration.internal-secret:}") String integrationSecret,
            @Value("${services.github-integration.connect-timeout:5s}") Duration connectTimeout,
            @Value("${services.github-integration.read-timeout:150s}") Duration readTimeout) {
        this(createIntegrationClient(builder, connectTimeout, readTimeout), userRepository,
                roleRepository, integrationBaseUrl, integrationSecret);
    }

    public GitHubIntegrationBffController(RestClient integrationClient, UserRepository userRepository,
            String integrationBaseUrl, String integrationSecret) {
        this(integrationClient, userRepository, null, integrationBaseUrl, integrationSecret);
    }

    public GitHubIntegrationBffController(RestClient integrationClient, UserRepository userRepository,
            RoleRepository roleRepository, String integrationBaseUrl, String integrationSecret) {
        this.integrationClient = integrationClient;
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.integrationBaseUrl = integrationBaseUrl.replaceAll("/+$", "");
        this.integrationSecret = integrationSecret == null ? "" : integrationSecret;
    }

    @Autowired(required = false)
    public void setWorkspaceRepository(WorkspaceRepository workspaceRepository) {
        this.workspaceRepository = workspaceRepository;
    }

    @Autowired(required = false)
    public void setWorkspaceMembershipRepository(WorkspaceMembershipRepository repository) {
        this.workspaceMembershipRepository = repository;
    }

    private static RestClient createIntegrationClient(RestClient.Builder builder,
            Duration connectTimeout, Duration readTimeout) {
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(connectTimeout);
        requestFactory.setReadTimeout(readTimeout);
        return builder.clone().requestFactory(requestFactory).build();
    }

    @RequestMapping
    public ResponseEntity<byte[]> proxy(HttpServletRequest incoming,
            Authentication authentication,
            @RequestBody(required = false) byte[] body) {
        if (authentication == null || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        if (integrationSecret.isBlank()) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "GitHub Integration internal credential is not configured.");
        }

        User user = authenticatedUser(authentication);
        String path = incoming.getRequestURI().substring(incoming.getContextPath().length());
        // Screen Authorization matrix: the account's role must be allowed to use this route at all.
        ApiRoutePermissions.Decision permission =
                ApiRoutePermissions.evaluate(incoming.getMethod(), path, user.getRole());
        if (!permission.allowed()) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, permission.reason());
        }
        Set<String> authorities = currentAuthorities(user, authentication);
        WorkspaceAuthorization workspaceAuthorization = verifiedWorkspaceForRequest(
                path, HttpMethod.valueOf(incoming.getMethod()), user, authorities);
        final String verifiedStaffTarget = HttpMethod.POST.matches(incoming.getMethod())
                && path.matches("/api/document-workflows/[^/]+/reassign")
                        ? verifyReassignmentTarget(body, authorities) : null;
        final String verifiedDelegate = HttpMethod.POST.matches(incoming.getMethod())
                && path.equals("/api/approval/delegations") ? verifyDelegate(body) : null;
        Matcher ownerRoute = DOCUMENT_OWNER_ROUTE.matcher(path);
        final String verifiedDocumentOwner = HttpMethod.PUT.matches(incoming.getMethod()) && ownerRoute.matches()
                ? verifyDocumentOwner(ownerRoute.group(1), ownerRoute.group(2)) : null;
        String query = incoming.getQueryString();
        URI target = URI.create(integrationBaseUrl + path + (query == null ? "" : "?" + query));
        HttpMethod method = HttpMethod.valueOf(incoming.getMethod());
        var request = integrationClient.method(method).uri(target);
        request.headers(headers -> {
            headers.setBearerAuth(integrationSecret);
            headers.set("X-User-Id", user.getId().toString());
            headers.set("X-User-Authorities", String.join(",", withWorkspaceScope(authorities, user)));
            if (workspaceAuthorization != null) {
                headers.set("X-Verified-Workspace-Id", workspaceAuthorization.targetWorkspaceId());
                headers.set("X-Verified-Workspace-Access", workspaceAuthorization.accessLevel());
                if (workspaceAuthorization.sourceWorkspaceId() != null) {
                    headers.set("X-Verified-Source-Workspace-Id",
                            workspaceAuthorization.sourceWorkspaceId());
                }
            }
            if (verifiedStaffTarget != null) {
                headers.set("X-Verified-Staff-User-Id", verifiedStaffTarget);
            }
            if (verifiedDelegate != null) {
                headers.set("X-Verified-Delegate-Id", verifiedDelegate);
            }
            if (verifiedDocumentOwner != null) {
                headers.set("X-Verified-Document-Owner-Id", verifiedDocumentOwner);
            }
            String contentType = incoming.getContentType();
            if (contentType != null) headers.set(HttpHeaders.CONTENT_TYPE, contentType);
            String accept = incoming.getHeader(HttpHeaders.ACCEPT);
            if (accept != null) headers.set(HttpHeaders.ACCEPT, accept);
        });
        if (body != null && body.length > 0) request.body(body);

        try {
            return request.exchange((outgoing, response) -> {
                HttpHeaders headers = new HttpHeaders();
                MediaType contentType = response.getHeaders().getContentType();
                if (contentType != null) headers.setContentType(contentType);
                for (String name : FORWARDED_RESPONSE_HEADERS) {
                    String value = response.getHeaders().getFirst(name);
                    if (value != null) headers.set(name, value);
                }
                byte[] responseBody = response.getBody().readAllBytes();
                return ResponseEntity.status(response.getStatusCode()).headers(headers).body(responseBody);
            });
        } catch (org.springframework.web.client.RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "GitHub Integration is unavailable.");
        }
    }

    private WorkspaceAuthorization verifiedWorkspaceForRequest(String path, HttpMethod method,
            User actor, Set<String> authorities) {
        Matcher collectionRoute = WORKSPACE_COLLECTION_ROUTE.matcher(path);
        if (collectionRoute.matches()) {
            String workspaceId = collectionRoute.group(1);
            return new WorkspaceAuthorization(workspaceId, null, verifiedWorkspaceAccess(workspaceId, actor, authorities));
        }
        Matcher workspaceRoute = WORKSPACE_REPOSITORY_ROUTE.matcher(path);
        if (workspaceRoute.matches()) {
            String targetWorkspaceId = workspaceRoute.group(1);
            String accessLevel = verifiedWorkspaceAccess(targetWorkspaceId, actor, authorities);
            if (!HttpMethod.GET.equals(method) || workspaceRoute.group(2) != null) {
                requireWorkspaceOwner(accessLevel);
            }
            String sourceWorkspaceId = null;
            if (HttpMethod.PUT.equals(method) && workspaceRoute.group(2) != null) {
                sourceWorkspaceId = resolveRepositoryWorkspace(
                        workspaceRoute.group(2), actor, authorities);
                requireWorkspaceOwner(verifiedWorkspaceAccess(sourceWorkspaceId, actor, authorities));
            }
            return new WorkspaceAuthorization(targetWorkspaceId, sourceWorkspaceId, accessLevel);
        }

        Matcher repositoryRoute = REPOSITORY_ID_ROUTE.matcher(path);
        if (!repositoryRoute.matches()) return null;
        String workspaceId = resolveRepositoryWorkspace(repositoryRoute.group(1), actor, authorities);
        String accessLevel = verifiedWorkspaceAccess(workspaceId, actor, authorities);
        boolean repositoryDetailRead = HttpMethod.GET.equals(method)
                && path.matches("^/api/repositories/[0-9a-fA-F-]{36}$");
        if (!repositoryDetailRead) requireWorkspaceOwner(accessLevel);
        return new WorkspaceAuthorization(workspaceId, null, accessLevel);
    }

    private String verifiedWorkspaceAccess(String workspaceId, User actor, Set<String> authorities) {
        if (workspaceId == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found");
        }
        if (workspaceId.equals("ws-" + actor.getId())) return "OWNER";
        boolean isAdmin = authorities.contains("ROLE_ADMINISTRATOR") || authorities.contains("ROLE_ADMIN");
        if (!isManagedWorkspaceId(workspaceId)) {
            if (isAdmin && workspaceId.startsWith("ws-")) {
                return "OWNER";
            }
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found");
        }
        if (workspaceRepository == null) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Workspace ownership verification is unavailable.");
        }
        if (workspaceRepository.findByIdAndOwner_Id(workspaceId, actor.getId()).isPresent()) return "OWNER";
        if (isAdmin && workspaceRepository.existsById(workspaceId)) return "OWNER";
        if (workspaceMembershipRepository == null
                || !workspaceMembershipRepository.existsByWorkspace_IdAndUser_IdAndUser_ActiveTrue(
                        workspaceId, actor.getId())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Workspace not found");
        }
        return "MEMBER";
    }

    private String verifyDocumentOwner(String workspaceId, String rawTargetId) {
        final long targetId;
        try {
            targetId = Long.parseLong(rawTargetId);
        } catch (NumberFormatException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid owner user id is required.");
        }
        if (targetId <= 0 || !rawTargetId.equals(Long.toString(targetId))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid owner user id is required.");
        }
        User target = userRepository.findById(targetId).filter(User::isActive)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "Select an active workspace owner or member."));
        try {
            verifiedWorkspaceAccess(workspaceId, target, Set.of());
        } catch (ResponseStatusException exception) {
            if (exception.getStatusCode() != HttpStatus.NOT_FOUND) throw exception;
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Select an active workspace owner or member.");
        }
        return rawTargetId;
    }

    private void requireWorkspaceOwner(String accessLevel) {
        if (!"OWNER".equals(accessLevel)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Workspace owner access is required.");
        }
    }

    private boolean isManagedWorkspaceId(String workspaceId) {
        if (workspaceId == null || !workspaceId.startsWith("workspace-")) return false;
        String rawUuid = workspaceId.substring("workspace-".length());
        try {
            return UUID.fromString(rawUuid).toString().equalsIgnoreCase(rawUuid);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private String resolveRepositoryWorkspace(String repositoryId, User actor, Set<String> authorities) {
        final UUID id;
        try {
            id = UUID.fromString(repositoryId);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Repository ID is invalid");
        }

        URI target = URI.create(integrationBaseUrl + "/api/internal/repositories/" + id + "/workspace");
        try {
            return integrationClient.get().uri(target).headers(headers -> {
                headers.setBearerAuth(integrationSecret);
                headers.set("X-User-Id", actor.getId().toString());
                headers.set("X-User-Authorities", String.join(",", authorities));
            }).exchange((outgoing, response) -> {
                int status = response.getStatusCode().value();
                if (status == HttpStatus.NOT_FOUND.value()) {
                    throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Repository not found");
                }
                if (status == HttpStatus.FORBIDDEN.value()) {
                    throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Repository access denied");
                }
                if (!response.getStatusCode().is2xxSuccessful()) {
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                            "Could not verify repository workspace ownership.");
                }
                if (response.getBody() == null) {
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                            "Repository response has no workspace identity.");
                }
                byte[] body = response.getBody().readAllBytes();
                try {
                    JsonNode json = objectMapper.readTree(body);
                    JsonNode workspaceId = json == null ? null : json.get("workspaceId");
                    if (workspaceId == null || !workspaceId.isTextual()
                            || workspaceId.textValue().isBlank()) {
                        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                                "Repository response has no workspace identity.");
                    }
                    return workspaceId.textValue();
                } catch (tools.jackson.core.JacksonException exception) {
                    throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                            "Repository response is invalid.");
                }
            });
        } catch (ResponseStatusException exception) {
            throw exception;
        } catch (org.springframework.web.client.RestClientException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                    "GitHub Integration is unavailable.");
        }
    }

    private record WorkspaceAuthorization(String targetWorkspaceId, String sourceWorkspaceId, String accessLevel) {
    }

    /**
     * The Manager who is to cover someone's approvals must exist, be active and be able to approve. The id is
     * checked here, where the accounts are, and passed on as X-Verified-Delegate-Id; GitHub Integration refuses
     * a delegation without it.
     */
    private String verifyDelegate(byte[] body) {
        if (body == null || body.length == 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Choose the Manager who covers your approvals.");
        }
        final JsonNode request;
        try {
            request = objectMapper.readTree(body);
        } catch (tools.jackson.core.JacksonException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The delegation request is invalid.");
        }
        JsonNode idNode = request == null ? null : request.get("delegateUserId");
        String raw = idNode == null || idNode.isNull() ? "" : idNode.asString("").trim();
        final long id;
        try {
            id = Long.parseLong(raw);
        } catch (NumberFormatException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid Manager user id is required.");
        }
        if (id < 1 || !raw.equals(Long.toString(id))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid Manager user id is required.");
        }
        User target = userRepository.findById(id).orElse(null);
        String roleName = target == null || target.getRole() == null ? "" : target.getRole().trim();
        if (roleName.startsWith("ROLE_")) roleName = roleName.substring("ROLE_".length());
        if (target == null || !target.isActive() || !"MANAGER".equals(roleName) || roleRepository == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The delegate must be an active Manager.");
        }
        boolean canApprove = roleRepository.findWithPermissionsByName("MANAGER")
                .map(role -> role.getPermissions().stream().map(permission -> permission.getCode())
                        .collect(Collectors.toSet()))
                .map(permissions -> permissions.contains("DOCUMENT_APPROVE")).orElse(false);
        if (!canApprove) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The Manager role cannot approve documents.");
        }
        return Long.toString(id);
    }

    private String verifyReassignmentTarget(byte[] body, Set<String> actorAuthorities) {
        if ((!actorAuthorities.contains("ROLE_ADMINISTRATOR") && !actorAuthorities.contains("ROLE_ADMIN"))
                || !actorAuthorities.contains("DOCUMENT_REASSIGN")) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Only an administrator with DOCUMENT_REASSIGN may reassign a review.");
        }
        if (body == null || body.length == 0) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A STAFF target and reason are required.");
        }
        final JsonNode request;
        try {
            request = objectMapper.readTree(body);
        } catch (tools.jackson.core.JacksonException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The reassign request is invalid.");
        }
        JsonNode targetIdNode = request == null ? null : request.get("targetStaffUserId");
        if (targetIdNode == null || !targetIdNode.isIntegralNumber()
                || !targetIdNode.canConvertToLong() || targetIdNode.longValue() < 1) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A valid STAFF user id is required.");
        }
        long targetId = targetIdNode.longValue();
        User target = userRepository.findById(targetId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST,
                        "The selected STAFF account does not exist."));
        String roleName = target.getRole() == null ? "" : target.getRole().trim();
        if (roleName.startsWith("ROLE_")) roleName = roleName.substring("ROLE_".length());
        if (!target.isActive() || !"STAFF".equals(roleName) || roleRepository == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "The selected user must be an active STAFF member.");
        }
        boolean canReview = roleRepository.findWithPermissionsByName("STAFF")
                .map(role -> role.getPermissions().stream().map(permission -> permission.getCode())
                        .collect(Collectors.toSet()))
                .map(permissions -> permissions.containsAll(Set.of("DOCUMENT_CLAIM", "DOCUMENT_REVIEW")))
                .orElse(false);
        if (!canReview) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "The STAFF role is missing review permissions.");
        }
        return Long.toString(targetId);
    }

    private Set<String> currentAuthorities(User user, Authentication authentication) {
        Set<String> result = new LinkedHashSet<>();
        String role = user.getRole() == null ? "" : user.getRole().trim();
        String normalized = role.startsWith("ROLE_") ? role.substring("ROLE_".length()) : role;
        if (!normalized.isBlank()) result.add("ROLE_" + normalized);
        if (roleRepository == null) {
            if (authentication.getAuthorities() != null) {
                authentication.getAuthorities().forEach(a -> result.add(a.getAuthority()));
            }
        } else if (!normalized.isBlank()) {
            roleRepository.findWithPermissionsByName(normalized).ifPresent(r ->
                    r.getPermissions().forEach(p -> result.add(p.getCode())));
        }
        return result.stream().filter(s -> s.matches("[A-Z0-9_]+"))
                .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    /**
     * Tells the GitHub Integration service which managed workspaces the caller belongs to
     * ({@code WORKSPACE:<id>}, or {@code WORKSPACE:*} for an administrator) so that document workflows
     * of other workspaces stay out of its queues and are not reachable by id.
     */
    private Set<String> withWorkspaceScope(Set<String> authorities, User user) {
        Set<String> result = new LinkedHashSet<>(authorities);
        if (authorities.contains("ROLE_ADMINISTRATOR") || authorities.contains("ROLE_ADMIN")) {
            result.add("WORKSPACE:*");
        } else if (workspaceRepository != null) {
            workspaceRepository.findAllAccessibleByUserId(user.getId())
                    .forEach(workspace -> result.add("WORKSPACE:" + workspace.getId()));
        }
        return result;
    }

    private User authenticatedUser(Authentication authentication) {
        if (authentication.getPrincipal() instanceof UserDetails details) {
            return userRepository.findByEmail(details.getUsername())
                    .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        }
        if (authentication.getPrincipal() instanceof OAuth2User oauthUser) {
            Object githubId = oauthUser.getAttribute("id");
            if (githubId != null) {
                return userRepository.findByGithubId(String.valueOf(githubId))
                        .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED));
            }
        }
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }
}