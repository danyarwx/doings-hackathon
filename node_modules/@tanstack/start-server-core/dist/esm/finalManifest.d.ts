import { Manifest } from '@tanstack/router-core';
import { HandlerInlineCssOption } from './inlineCss.js';
import { StartManifestWithClientEntry, TransformAssets } from './transformAssetUrls.js';
export type { HandlerInlineCssOption, StartManifestWithClientEntry, TransformAssets, };
export interface FinalManifestOptions {
    /**
     * Controls whether Start inlines build-collected CSS by default at runtime.
     *
     * This only has an effect when the build was created with
     * `server.build.inlineCss` enabled. Pass a callback to decide per request.
     * `handler(request, { inlineCss })` overrides this value for that request.
     *
     * @default true
     */
    inlineCss?: HandlerInlineCssOption;
    /**
     * Transform manifest-managed asset URLs and attributes at runtime, e.g. to
     * prepend a CDN prefix.
     *
     * This covers JS preloads, CSS links, the client entry script, and URLs
     * inside build-collected inline CSS. Asset imports used directly in
     * components should be handled by the bundler instead.
     */
    transformAssets?: TransformAssets;
}
export type GetBaseManifest = () => Promise<StartManifestWithClientEntry>;
export interface FinalManifestRequestOptions {
    request: Request;
    requestInlineCss: boolean | undefined;
    getBaseManifest: GetBaseManifest;
}
export interface FinalManifestResolver {
    warmup: (opts: {
        getBaseManifest: GetBaseManifest;
    }) => Promise<Manifest> | undefined;
    resolveCached: (opts: FinalManifestRequestOptions) => Promise<Manifest>;
    resolveUncached: (opts: FinalManifestRequestOptions) => Promise<Manifest>;
}
export declare function createCachedBaseManifestLoader(loadBaseManifest: GetBaseManifest): GetBaseManifest;
export declare function createFinalManifestResolver(opts: FinalManifestOptions & {
    cacheCreateTransform: boolean;
}): FinalManifestResolver;
