import json
import time
from typing import Optional
from urllib.parse import quote_plus
from fastmcp import FastMCP
from playwright.sync_api import sync_playwright

# ============================================================
# Serveur MCP Reddit — Permet à Claude de rechercher sur Reddit
# ============================================================

mcp = FastMCP(
    "RedditSearch",
    instructions=(
        "Serveur MCP pour rechercher et analyser Reddit. "
        "Outils disponibles : search_reddit (browse subreddits), "
        "search_reddit_query (recherche par mots-clés), "
        "get_post_comments (commentaires d'un post), "
        "get_post_details (contenu complet d'un post), "
        "get_subreddit_info (infos sur un subreddit), "
        "analyze_opportunities (scoring business)."
    )
)

# --- Configuration par défaut ---
DEFAULT_SUBREDDITS = [
    "SomebodyMakeThis",
    "StartupIdeas",
    "businessideas",
    "Entrepreneur",
    "saas",
    "technology",
    "antiwork"
]

MONEY_KEYWORDS = [
    "pay", "buy", "subscription", "charge", "business", "revenue",
    "monetize", "earn", "dollar", "pricing", "freemium", "saas",
    "startup", "mvp", "profit", "cost", "budget", "invest",
    "funding", "money", "income", "sale", "customer"
]
IMPACT_KEYWORDS = [
    "problem", "fix", "stop", "change", "community", "alternative",
    "sick of", "hate", "scam", "frustrated", "annoying", "broken",
    "need", "wish", "want", "missing", "terrible", "worst",
    "replace", "better than", "should exist", "why isn't there",
    "someone should make", "idea", "solution", "pain point"
]

# --- Utilitaires internes ---

def _create_browser_context(playwright):
    """Crée un contexte navigateur Playwright avec un user-agent réaliste."""
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    )
    # Bloquer les images et médias pour aller plus vite
    context.route("**/*.{png,jpg,jpeg,gif,svg,webp,mp4,webm}", lambda route: route.abort())
    return browser, context


def _safe_int(value, default: int = 0) -> int:
    """Convertit en int de manière sûre."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _extract_posts_from_page(page, max_scrolls: int = 4) -> list[dict]:
    """Scroll la page et extrait tous les posts Reddit visibles."""
    for i in range(max_scrolls):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5 + (i * 0.3))  # Délai progressif pour stabilité
        except Exception:
            break

    posts = []
    seen_urls = set()  # Déduplication
    elements = page.locator("shreddit-post").all()

    for el in elements:
        title = el.get_attribute("post-title")
        if not title:
            continue

        permalink = el.get_attribute("permalink")
        url = f"https://www.reddit.com{permalink}" if permalink else None

        # Déduplication par URL
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        score = _safe_int(el.get_attribute("score"))
        num_comments = _safe_int(el.get_attribute("comment-count"))
        author = el.get_attribute("author") or "unknown"

        # Extraction du flair si disponible
        flair = el.get_attribute("flair-text") or None

        # Type de post (link, self, image, video)
        content_href = el.get_attribute("content-href") or ""
        if "reddit.com" in content_href or not content_href:
            post_type = "self"
        elif any(ext in content_href for ext in [".jpg", ".png", ".gif", ".webp"]):
            post_type = "image"
        elif any(ext in content_href for ext in [".mp4", "youtu", "vimeo"]):
            post_type = "video"
        else:
            post_type = "link"

        # Timestamp relatif
        created = el.get_attribute("created-timestamp") or None

        posts.append({
            "title": title,
            "score": score,
            "num_comments": num_comments,
            "author": author,
            "url": url,
            "flair": flair,
            "post_type": post_type,
            "created": created
        })

    return posts


def _calculate_opportunity_score(title: str, score: int, num_comments: int) -> int:
    """
    Calcule le score d'opportunité business d'un post.
    Prend en compte : popularité, engagement, et pertinence sémantique.
    """
    # Score de base pondéré
    base_score = (score * 2) + (num_comments * 3)

    # Ratio d'engagement (beaucoup de commentaires vs upvotes = discussion active)
    if score > 0:
        engagement_ratio = num_comments / score
        if engagement_ratio > 0.3:  # Post très discuté
            base_score = int(base_score * 1.3)
        elif engagement_ratio > 0.15:
            base_score = int(base_score * 1.15)

    # Bonus mots-clés (cumulatifs)
    title_lower = title.lower()
    money_hits = sum(1 for kw in MONEY_KEYWORDS if kw in title_lower)
    impact_hits = sum(1 for kw in IMPACT_KEYWORDS if kw in title_lower)

    base_score += money_hits * 15
    base_score += impact_hits * 20

    # Super bonus si les deux catégories sont touchées
    if money_hits > 0 and impact_hits > 0:
        base_score = int(base_score * 1.25)

    return base_score


# ============================================================
# OUTIL 1 : Rechercher des posts sur un ou plusieurs subreddits
# ============================================================

@mcp.tool()
def search_reddit(
    subreddits: list[str],
    sort: str = "hot",
    time_filter: str = "day",
    limit: int = 25,
    keywords: Optional[list[str]] = None
) -> str:
    """
    Recherche des posts sur un ou plusieurs subreddits Reddit.

    Args:
        subreddits: Liste des subreddits à scanner (ex: ["python", "webdev"]).
        sort: Méthode de tri — "hot", "new", "top", "rising".
        time_filter: Filtre temporel pour "top" — "hour", "day", "week", "month", "year", "all".
        limit: Nombre maximum de posts à retourner au total.
        keywords: Mots-clés optionnels pour filtrer les résultats par titre.

    Returns:
        JSON avec les posts trouvés, incluant titre, score, commentaires, auteur, URL, flair et type.
    """
    all_posts = []
    errors = []

    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        for sub in subreddits:
            if sort == "top":
                url = f"https://www.reddit.com/r/{sub}/top/?t={time_filter}"
            else:
                url = f"https://www.reddit.com/r/{sub}/{sort}/"

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)

                posts = _extract_posts_from_page(page, max_scrolls=4)

                for post in posts:
                    post["subreddit"] = sub

                    if keywords:
                        title_lower = post["title"].lower()
                        if not any(kw.lower() in title_lower for kw in keywords):
                            continue

                    all_posts.append(post)

            except Exception as e:
                errors.append(f"r/{sub}: {str(e)[:100]}")

            time.sleep(1.5)

        browser.close()

    all_posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    all_posts = all_posts[:limit]

    result = {
        "total_results": len(all_posts),
        "subreddits_scanned": subreddits,
        "sort": sort,
        "posts": all_posts
    }
    if errors:
        result["errors"] = errors

    return json.dumps(result, indent=2, ensure_ascii=False)


# ============================================================
# OUTIL 2 : Recherche Reddit par mots-clés (barre de recherche)
# ============================================================

@mcp.tool()
def search_reddit_query(
    query: str,
    sort: str = "relevance",
    time_filter: str = "week",
    subreddit: Optional[str] = None,
    limit: int = 25
) -> str:
    """
    Recherche sur Reddit par mots-clés via la page de recherche Reddit.

    Args:
        query: Texte de recherche (ex: "best python framework 2025").
        sort: Tri des résultats — "relevance", "hot", "top", "new", "comments".
        time_filter: Filtre temporel — "hour", "day", "week", "month", "year", "all".
        subreddit: Optionnel — limiter la recherche à un subreddit spécifique.
        limit: Nombre maximum de résultats à retourner.

    Returns:
        JSON avec les résultats de recherche Reddit.
    """
    all_posts = []
    encoded_query = quote_plus(query)

    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        if subreddit:
            url = (
                f"https://www.reddit.com/r/{subreddit}/search/"
                f"?q={encoded_query}&sort={sort}&t={time_filter}&restrict_sr=1"
            )
        else:
            url = (
                f"https://www.reddit.com/search/"
                f"?q={encoded_query}&sort={sort}&t={time_filter}"
            )

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)

            posts = _extract_posts_from_page(page, max_scrolls=3)

            for post in posts:
                if post.get("url"):
                    parts = post["url"].split("/r/")
                    if len(parts) > 1:
                        post["subreddit"] = parts[1].split("/")[0]

                all_posts.append(post)

        except Exception as e:
            browser.close()
            return json.dumps({
                "error": f"Erreur lors de la recherche: {str(e)}",
                "query": query
            }, indent=2, ensure_ascii=False)

        browser.close()

    all_posts = all_posts[:limit]

    return json.dumps({
        "total_results": len(all_posts),
        "query": query,
        "sort": sort,
        "time_filter": time_filter,
        "posts": all_posts
    }, indent=2, ensure_ascii=False)


# ============================================================
# OUTIL 3 : Récupérer les commentaires d'un post spécifique
# ============================================================

@mcp.tool()
def get_post_comments(
    post_url: str,
    limit: int = 20
) -> str:
    """
    Récupère les commentaires d'un post Reddit spécifique.

    Args:
        post_url: URL complète du post Reddit.
        limit: Nombre maximum de commentaires à retourner.

    Returns:
        JSON avec le titre du post et ses commentaires (auteur, texte, score, profondeur).
    """
    comments = []

    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)

            # Extraire les infos du post
            post_title = ""
            post_score = 0
            post_el = page.locator("shreddit-post").first
            if post_el.count():
                post_title = post_el.get_attribute("post-title") or ""
                post_score = _safe_int(post_el.get_attribute("score"))

            # Extraire le contenu textuel du post (selftext)
            post_body = ""
            try:
                body_el = page.locator("[slot='text-body'] p, .md p").all()
                if body_el:
                    post_body = "\n".join(
                        t.inner_text() for t in body_el[:10] if t.inner_text().strip()
                    )
            except Exception:
                pass

            # Extraire les commentaires
            comment_elements = page.locator("shreddit-comment").all()

            for el in comment_elements[:limit]:
                author = el.get_attribute("author") or "unknown"
                score_attr = el.get_attribute("score")
                depth = el.get_attribute("depth") or "0"

                # Extraction du texte avec plusieurs sélecteurs pour robustesse
                comment_text = ""
                for selector in [
                    "div[slot='comment'] p",
                    "div[id*='comment-content'] p",
                    "div.md p",
                    "p"
                ]:
                    try:
                        text_els = el.locator(selector).all()
                        if text_els:
                            comment_text = " ".join(
                                t.inner_text() for t in text_els if t.inner_text().strip()
                            )
                            if comment_text.strip():
                                break
                    except Exception:
                        continue

                if comment_text.strip():
                    comments.append({
                        "author": author,
                        "text": comment_text.strip()[:2000],  # Limiter la taille
                        "score": _safe_int(score_attr),
                        "depth": _safe_int(depth)
                    })

        except Exception as e:
            browser.close()
            return json.dumps({
                "error": f"Erreur: {str(e)}",
                "post_url": post_url
            }, indent=2, ensure_ascii=False)

        browser.close()

    return json.dumps({
        "post_url": post_url,
        "post_title": post_title,
        "post_score": post_score,
        "post_body": post_body[:3000] if post_body else None,
        "total_comments": len(comments),
        "comments": comments
    }, indent=2, ensure_ascii=False)


# ============================================================
# OUTIL 4 : Contenu complet d'un post Reddit
# ============================================================

@mcp.tool()
def get_post_details(
    post_url: str
) -> str:
    """
    Récupère le contenu complet d'un post Reddit : titre, auteur, score,
    texte du post (selftext), flair, nombre de commentaires et métadonnées.

    Args:
        post_url: URL complète du post Reddit.

    Returns:
        JSON avec tous les détails du post.
    """
    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)

            post_el = page.locator("shreddit-post").first
            if not post_el.count():
                browser.close()
                return json.dumps({
                    "error": "Post non trouvé sur cette page",
                    "post_url": post_url
                }, indent=2, ensure_ascii=False)

            title = post_el.get_attribute("post-title") or ""
            author = post_el.get_attribute("author") or "unknown"
            score = _safe_int(post_el.get_attribute("score"))
            num_comments = _safe_int(post_el.get_attribute("comment-count"))
            flair = post_el.get_attribute("flair-text") or None
            created = post_el.get_attribute("created-timestamp") or None
            subreddit_name = post_el.get_attribute("subreddit-prefixed-name") or None

            # Extraire le selftext (contenu textuel du post)
            selftext = ""
            try:
                body_els = page.locator(
                    "[slot='text-body'] p, "
                    "[slot='text-body'] li, "
                    "[slot='text-body'] h1, "
                    "[slot='text-body'] h2, "
                    "[slot='text-body'] h3, "
                    ".md p, .md li"
                ).all()
                if body_els:
                    selftext = "\n".join(
                        el.inner_text() for el in body_els[:50] if el.inner_text().strip()
                    )
            except Exception:
                pass

            # Extraire l'URL externe si c'est un post lien
            external_url = None
            content_href = post_el.get_attribute("content-href") or ""
            if content_href and "reddit.com" not in content_href:
                external_url = content_href

            result = {
                "post_url": post_url,
                "title": title,
                "author": author,
                "subreddit": subreddit_name,
                "score": score,
                "num_comments": num_comments,
                "flair": flair,
                "created": created,
                "selftext": selftext[:5000] if selftext else None,
                "external_url": external_url
            }

        except Exception as e:
            browser.close()
            return json.dumps({
                "error": f"Erreur: {str(e)}",
                "post_url": post_url
            }, indent=2, ensure_ascii=False)

        browser.close()

    return json.dumps(result, indent=2, ensure_ascii=False)


# ============================================================
# OUTIL 5 : Informations sur un subreddit
# ============================================================

@mcp.tool()
def get_subreddit_info(
    subreddit: str
) -> str:
    """
    Récupère les informations publiques d'un subreddit : description,
    nombre de membres, posts populaires récents.

    Args:
        subreddit: Nom du subreddit (sans le r/, ex: "python").

    Returns:
        JSON avec les infos du subreddit et ses 5 top posts actuels.
    """
    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        try:
            url = f"https://www.reddit.com/r/{subreddit}/"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)

            # Extraire les infos de la sidebar / header
            info = {
                "subreddit": f"r/{subreddit}",
                "url": url,
                "name": None,
                "description": None,
                "members": None,
                "online": None,
                "created": None
            }

            # Nombre de membres (attribut sur l'élément communauté)
            try:
                members_el = page.locator(
                    "shreddit-subreddit-header__subscribers, "
                    "[id*='subscriber'], "
                    "faceplate-number[pretty]"
                ).first
                if members_el.count():
                    info["members"] = members_el.get_attribute("number") or members_el.inner_text()
            except Exception:
                pass

            # Description du subreddit
            try:
                desc_selectors = [
                    "[data-testid='subreddit-description']",
                    ".public-description",
                    "div[slot='md'] p",
                    "shreddit-async-loader[bundlename='sidebar'] p"
                ]
                for sel in desc_selectors:
                    desc_el = page.locator(sel).first
                    if desc_el.count():
                        info["description"] = desc_el.inner_text().strip()[:500]
                        break
            except Exception:
                pass

            # Top 5 posts actuels
            posts = _extract_posts_from_page(page, max_scrolls=1)
            top_posts = sorted(posts, key=lambda x: x.get("score", 0), reverse=True)[:5]

            info["top_posts"] = top_posts

        except Exception as e:
            browser.close()
            return json.dumps({
                "error": f"Erreur: {str(e)}",
                "subreddit": subreddit
            }, indent=2, ensure_ascii=False)

        browser.close()

    return json.dumps(info, indent=2, ensure_ascii=False)


# ============================================================
# OUTIL 6 : Analyser les opportunités business sur Reddit
# ============================================================

@mcp.tool()
def analyze_opportunities(
    subreddits: Optional[list[str]] = None,
    min_score: int = 100,
    limit: int = 30,
    keywords: Optional[list[str]] = None
) -> str:
    """
    Analyse des posts Reddit pour identifier des opportunités business.
    Score basé sur : popularité (upvotes), engagement (commentaires),
    et pertinence sémantique (mots-clés argent + problèmes).

    Args:
        subreddits: Subreddits à analyser (défaut: SomebodyMakeThis, StartupIdeas, businessideas, Entrepreneur, saas, technology, antiwork).
        min_score: Score d'opportunité minimum pour inclure un post.
        limit: Nombre maximum de résultats à retourner.
        keywords: Mots-clés supplémentaires pour filtrer les posts.

    Returns:
        JSON avec les posts triés par score d'opportunité décroissant, incluant des statistiques.
    """
    if subreddits is None:
        subreddits = DEFAULT_SUBREDDITS

    all_ideas = []
    errors = []
    total_scanned = 0

    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/hot/"

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)

                posts = _extract_posts_from_page(page, max_scrolls=5)
                total_scanned += len(posts)

                for post in posts:
                    if keywords:
                        title_lower = post["title"].lower()
                        if not any(kw.lower() in title_lower for kw in keywords):
                            continue

                    opp_score = _calculate_opportunity_score(
                        post["title"], post["score"], post["num_comments"]
                    )

                    if opp_score >= min_score:
                        all_ideas.append({
                            "subreddit": sub,
                            "title": post["title"],
                            "opportunity_score": opp_score,
                            "reddit_score": post["score"],
                            "num_comments": post["num_comments"],
                            "engagement_ratio": round(
                                post["num_comments"] / max(post["score"], 1), 3
                            ),
                            "author": post["author"],
                            "flair": post.get("flair"),
                            "url": post["url"]
                        })

            except Exception as e:
                errors.append(f"r/{sub}: {str(e)[:100]}")

            time.sleep(1.5)

        browser.close()

    # Trier par score d'opportunité décroissant
    all_ideas.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
    all_ideas = all_ideas[:limit]

    # Statistiques enrichies
    high_score_count = sum(1 for x in all_ideas if x.get("opportunity_score", 0) >= 1000)
    avg_score = (
        round(sum(x.get("opportunity_score", 0) for x in all_ideas) / len(all_ideas))
        if all_ideas else 0
    )

    result = {
        "total_results": len(all_ideas),
        "total_posts_scanned": total_scanned,
        "high_score_ideas": high_score_count,
        "average_opportunity_score": avg_score,
        "min_score_filter": min_score,
        "subreddits_scanned": subreddits,
        "ideas": all_ideas
    }
    if errors:
        result["errors"] = errors

    return json.dumps(result, indent=2, ensure_ascii=False)


# ============================================================
# Point d'entrée
# ============================================================

if __name__ == "__main__":
    mcp.run()