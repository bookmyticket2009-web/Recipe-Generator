document.addEventListener("DOMContentLoaded", () => {
    if (window.location.port === "5000") {
        const adminNav = document.querySelector('a[data-nav="admin"]');
        if (adminNav) adminNav.style.display = "none";
    }

    checkCurrentUser();
    fetchTodaysPick();
    fetchRecipes();
    setupSearchBar();
    setupCategoryFilters();
    setupGlobalFavoriteListener();
    setupViewAllButton();
    setupAuthModal();
    setupFridgeManager();
    setupMobileDrawer();
    setupIntegratedAIChef();
    setupRecipeRoulette();
    setupRecipeSubmission();
    setupAdminAuth();
    handleUrlRecipeHash();

    // 🚀 Auto-load admin submissions on page load if the admin section is visible
    const adminSection = document.getElementById("adminSection");
    if (adminSection && adminSection.style.display !== "none") {
        checkAdminSession();
    }
});

let currentTag = "all";
let searchQuery = "";
let currentRecipeKey = null;
let allFetchedRecipes = [];
let isExpanded = false;
const INITIAL_LIMIT = 6;
let fridgeItems = [];
let isSubmittingChef = false; 

function renderMarkdown(text) {
    if (!text) return "";
    try {
        if (typeof marked !== "undefined" && marked.parse) {
            return marked.parse(text);
        }
    } catch (e) {
        console.error("Marked parsing error:", e);
    }

    let lines = text.split("\n");
    let formatted = lines.map((line) => {
        let trimmed = line.trim();
        if (trimmed.startsWith("### ")) return `<h3>${trimmed.replace("### ", "")}</h3>`;
        if (trimmed.startsWith("## ")) return `<h2>${trimmed.replace("## ", "")}</h2>`;
        if (trimmed.startsWith("# ")) return `<h1>${trimmed.replace("# ", "")}</h1>`;
        return line;
    });

    return formatted.join("<br>");
}

function setupCategoryFilters() {
    const navLinks = document.querySelectorAll("#sideNav a");
    const categoryBtns = document.querySelectorAll(".cat");
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");

    const tagMapping = {
        "home": "all",
        "bakery": "bakery",
        "food": "main course",
        "drinks": "beverages"
    };

    navLinks.forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const dataNav = btn.getAttribute("data-nav");
            if (dataNav === "roulette") return;

            navLinks.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            if (sidebar) sidebar.classList.remove("show");
            if (overlay) overlay.classList.remove("show");

            const homeView = document.getElementById("homeView");
            const fridgeSection = document.getElementById("aiFridgeSection");
            const chefSection = document.getElementById("aiChefSection");
            const submitSection = document.getElementById("submitRecipeSection");
            const adminSection = document.getElementById("adminSection");

            if (homeView) homeView.style.display = "none";
            if (fridgeSection) fridgeSection.style.display = "none";
            if (chefSection) chefSection.style.display = "none";
            if (submitSection) submitSection.style.display = "none";
            if (adminSection) adminSection.style.display = "none";

            if (dataNav === "fridge") {
                if (fridgeSection) fridgeSection.style.display = "block";
            } else if (dataNav === "chef") {
                if (chefSection) chefSection.style.display = "block";
            } else if (dataNav === "submit") {
                if (submitSection) {
                    submitSection.style.display = "block";
                    loadMySubmissionsTracker();
                }
            } else if (dataNav === "admin") {
                if (adminSection) adminSection.style.display = "block";
                checkAdminSession();
                loadAdminSubmissions(); 
            } else {
                if (homeView) homeView.style.display = "block";
                currentTag = tagMapping[dataNav] || dataNav;
                isExpanded = false;
                fetchRecipes();
            }
        });
    });

    categoryBtns.forEach((cat) => {
        cat.addEventListener("click", () => {
            const filter = cat.getAttribute("data-filter");
            categoryBtns.forEach((c) => c.classList.remove("active"));
            cat.classList.add("active");
            currentTag = filter;
            isExpanded = false;
            fetchRecipes();
        });
    });
}

function setupAdminAuth() {
    const adminLoginForm = document.getElementById("adminLoginForm");
    const adminLogoutBtn = document.getElementById("adminLogoutBtn");

    if (adminLoginForm) {
        adminLoginForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const id = document.getElementById("adminIdInput").value;
            const password = document.getElementById("adminPasswordInput").value;
            const errDiv = document.getElementById("adminLoginError");
            errDiv.textContent = "";

            try {
                const res = await fetch("/api/admin/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ id, password })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error);

                document.getElementById("adminLoginBox").style.display = "none";
                document.getElementById("adminDashboardContent").style.display = "block";
                loadAdminSubmissions();
            } catch (err) {
                errDiv.textContent = err.message;
            }
        });
    }

    if (adminLogoutBtn) {
        adminLogoutBtn.addEventListener("click", async () => {
            await fetch("/api/admin/logout", { method: "POST" });
            document.getElementById("adminDashboardContent").style.display = "none";
            document.getElementById("adminLoginBox").style.display = "block";
            document.getElementById("adminIdInput").value = "";
            document.getElementById("adminPasswordInput").value = "";
        });
    }
}

async function checkAdminSession() {
    try {
        const res = await fetch("/api/admin/check");
        const data = await res.json();
        if (data.is_admin) {
            document.getElementById("adminLoginBox").style.display = "none";
            document.getElementById("adminDashboardContent").style.display = "block";
            loadAdminSubmissions();
        } else {
            document.getElementById("adminLoginBox").style.display = "block";
            document.getElementById("adminDashboardContent").style.display = "none";
        }
    } catch (err) {
        console.error("Admin check failed:", err);
    }
}

async function loadAdminSubmissions() {
    const container = document.getElementById("adminSubmissionsList");
    if (!container) return;

    try {
        const res = await fetch("/api/admin/submissions");
        if (!res.ok) throw new Error("Unauthorized");
        const items = await res.json();

        if (!items || items.length === 0) {
            container.innerHTML = `<p style="color: var(--slate-600); padding: 10px;">No recipe submissions found.</p>`;
            return;
        }

        container.innerHTML = items.map(sub => `
            <div style="background: var(--surface-cream); border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: 20px; display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="font-size: 16px; font-weight: 800; color: var(--slate-900);">${sub.title} <span style="font-size: 11px; padding: 3px 8px; border-radius: 10px; background: ${sub.ai_status === 'New' ? '#dcfce7' : '#fee2e2'}; color: ${sub.ai_status === 'New' ? '#166534' : '#991b1b'}; margin-left: 8px;">AI: ${sub.ai_status || 'New'}</span></h3>
                    <span style="font-size: 12px; font-weight: 700; color: ${sub.approval_status === 'Approved' ? '#16a34a' : (sub.approval_status === 'Rejected' ? '#dc2626' : '#d97706')};">Status: ${sub.approval_status}</span>
                </div>
                <p style="font-size: 13px; color: var(--slate-600);"><b>Category:</b> ${sub.tag} | <b>Time:</b> ${sub.time} | <b>Calories:</b> ${sub.kcal} kcal | <b>Submitted By:</b> <b>${sub.submitted_by}</b></p>
                <p style="font-size: 13px; color: var(--slate-900);"><b>Description:</b> ${sub.desc}</p>
                <p style="font-size: 12px; color: var(--slate-600);"><b>AI Reasoning:</b> ${sub.ai_reason || 'N/A'}</p>
                ${sub.approval_status === 'Rejected' ? `<p style="font-size: 12px; color: #dc2626;"><b>Rejection Reason:</b> ${sub.rejection_reason}</p>` : ''}
                ${sub.approval_status === 'Pending' ? `
                    <div style="display: flex; gap: 10px; margin-top: 8px; align-items: center; flex-wrap: wrap;">
                        <button onclick="reviewSubmission(${sub.id}, 'approve')" style="background: #16a34a; color: white; border: none; padding: 8px 16px; border-radius: var(--radius-sm); font-weight: 700; cursor: pointer;">Approve & Publish</button>
                        <div style="display: flex; gap: 6px; flex: 1;">
                            <input type="text" id="reason_${sub.id}" placeholder="Enter reason for rejection..." style="flex: 1; padding: 6px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-light); font-size: 12px; outline: none;">
                            <button onclick="rejectWithReason(${sub.id})" style="background: #dc2626; color: white; border: none; padding: 8px 16px; border-radius: var(--radius-sm); font-weight: 700; cursor: pointer;">Reject</button>
                        </div>
                    </div>
                ` : ''}
            </div>
        `).join("");
    } catch (err) {
        console.error("Admin load error:", err);
        container.innerHTML = `<p style="color: #dc2626;">Failed to load submissions or unauthorized access.</p>`;
    }
}

async function reviewSubmission(id, action) {
    try {
        const res = await fetch(`/api/admin/submissions/${id}/${action}`, { method: "POST" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        loadAdminSubmissions();
    } catch (err) {
        alert(`Action failed: ${err.message}`);
    }
}

async function rejectWithReason(id) {
    const reasonInput = document.getElementById(`reason_${id}`);
    const reason = reasonInput ? reasonInput.value.trim() : "No reason provided.";

    if (!reason) {
        alert("Please provide a reason for rejection.");
        return;
    }

    try {
        const res = await fetch(`/api/admin/submissions/${id}/reject`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        loadAdminSubmissions();
    } catch (err) {
        alert(`Rejection failed: ${err.message}`);
    }
}

function setupRecipeSubmission() {
    const submitForm = document.getElementById("submitRecipeForm");
    if (!submitForm) return;

    submitForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const msg = document.getElementById("subResultMsg");

        const authRes = await fetch("/api/auth/me");
        const authData = await authRes.json();

        if (!authData.logged_in) {
            msg.style.color = "#dc2626";
            msg.textContent = "❌ You must be logged in to submit new recipes. Please click the profile icon at the top right to login or sign up!";
            const authModal = document.getElementById("authModal");
            if (authModal) authModal.classList.add("show");
            return;
        }

        const title = document.getElementById("subTitle").value;
        const tag = document.getElementById("subTag").value;
        const time = document.getElementById("subTime").value;
        const kcal = document.getElementById("subKcal").value;
        const desc = document.getElementById("subDesc").value;
        const instructions = document.getElementById("subInstructions").value;

        msg.style.color = "#475569";
        msg.textContent = `🤖 Processing recipe submission...`;

        try {
            const res = await fetch("/api/recipes/submit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title, tag, time, kcal, desc, instructions })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Submission failed");

            msg.style.color = "#16a34a";
            msg.textContent = `✅ ${data.message}`;
            submitForm.reset();
            loadMySubmissionsTracker();
        } catch (err) {
            msg.style.color = "#dc2626";
            msg.textContent = `❌ Error: ${err.message}`;
        }
    });
}

async function loadMySubmissionsTracker() {
    const trackerContainer = document.getElementById("mySubmissionsTracker");
    if (!trackerContainer) return;

    try {
        const res = await fetch("/api/recipes/my-submissions");
        if (!res.ok) {
            trackerContainer.innerHTML = `<p style="color: var(--slate-600); font-size: 13px;">Log in to view your submission history and statuses. <a href="#" onclick="document.getElementById('authModal').classList.add('show'); return false;" style="color: var(--primary); font-weight: bold;">Click here to login</a></p>`;
            return;
        }
        const items = await res.json();

        if (!items || items.length === 0) {
            trackerContainer.innerHTML = `<p style="color: var(--slate-600); font-size: 13px;">You haven't submitted any recipes yet.</p>`;
            return;
        }

        trackerContainer.innerHTML = items.map(sub => {
            let statusColor = '#d97706'; 
            if (sub.approval_status === 'Approved') statusColor = '#16a34a'; 
            if (sub.approval_status === 'Rejected') statusColor = '#dc2626'; 

            return `
                <div style="background: var(--surface-alt); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <b style="font-size: 14.5px; color: var(--slate-900);">${sub.title}</b>
                        <span style="font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 12px; background: #fff; border: 1px solid ${statusColor}; color: ${statusColor};">Status: ${sub.approval_status}</span>
                    </div>
                    <p style="font-size: 12.5px; color: var(--slate-600);">Category: <b>${sub.tag}</b> | Time: <b>${sub.time}</b> | Calories: <b>${sub.kcal} kcal</b></p>
                    ${sub.approval_status === 'Rejected' ? `<p style="font-size: 12px; color: #dc2626; background: #fee2e2; padding: 8px 12px; border-radius: 6px;"><b>Rejection Reason from Admin:</b> ${sub.rejection_reason || 'No reason provided.'}</p>` : ''}
                    ${sub.approval_status === 'Approved' ? `<p style="font-size: 12px; color: #166534; background: #dcfce7; padding: 8px 12px; border-radius: 6px;">🎉 Congratulations! Your recipe has been published to the live CookEase database.</p>` : ''}
                    ${sub.approval_status === 'Pending' ? `<p style="font-size: 12px; color: #d97706; background: #fef3c7; padding: 8px 12px; border-radius: 6px;">⏳ Your recipe is currently under review by our culinary admins.</p>` : ''}
                </div>
            `;
        }).join("");
    } catch (err) {
        console.error("Failed to load user submissions tracker", err);
        trackerContainer.innerHTML = `<p style="color: #dc2626; font-size: 13px;">Could not load submission history.</p>`;
    }
}

function setupFridgeManager() {
    const input = document.getElementById("fridgeInput");
    const addBtn = document.getElementById("addFridgeItemBtn");
    const matchBtn = document.getElementById("matchRecipesBtn");
    const generateBtn = document.getElementById("generateAIRecipeBtn");

    if (addBtn && input) {
        addBtn.addEventListener("click", () => {
            if (input.value.trim()) {
                addIngredient(input.value.trim());
                input.value = "";
            }
        });
        input.addEventListener("keypress", (e) => {
            if (e.key === "Enter" && input.value.trim()) {
                addIngredient(input.value.trim());
                input.value = "";
            }
        });
    }

    if (matchBtn) {
        matchBtn.addEventListener("click", async () => {
            if (fridgeItems.length === 0) return;
            matchBtn.textContent = "✨ Searching Recipes...";
            matchBtn.disabled = true;

            try {
                const response = await fetch("/api/fridge/match", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ingredients: fridgeItems }),
                });

                if (!response.ok) throw new Error("Match search failed");
                allFetchedRecipes = await response.json();

                const homeView = document.getElementById("homeView");
                const fridgeSection = document.getElementById("aiFridgeSection");
                const navLinks = document.querySelectorAll("#sideNav a");

                if (homeView) homeView.style.display = "block";
                if (fridgeSection) fridgeSection.style.display = "none";

                navLinks.forEach((b) => b.classList.remove("active"));
                const homeLink = document.querySelector('#sideNav a[data-nav="home"]');
                if (homeLink) homeLink.classList.add("active");

                renderPopularRecipes();
                if (allFetchedRecipes.length > 0)
                    loadRecipeDetails(allFetchedRecipes[0].key);
                else clearRecipeDetails();
            } catch (err) {
                console.error("Match error:", err);
            } finally {
                matchBtn.textContent = "✨ Match DB Recipes";
                matchBtn.disabled = false;
            }
        });
    }

    if (generateBtn) {
        generateBtn.addEventListener("click", async () => {
            if (fridgeItems.length === 0) return;
            generateBtn.textContent = "🤖 Generating Recipe...";
            generateBtn.disabled = true;

            try {
                const response = await fetch("/api/ai-chef/generate-recipe", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ ingredients: fridgeItems }),
                });

                const data = await response.json();
                if (!response.ok) throw new Error(data.error || "Generation failed");

                const chefLink = document.querySelector('#sideNav a[data-nav="chef"]');
                if (chefLink) chefLink.click();

                const chatBox = document.getElementById("chefChatBox");
                if (chatBox) {
                    const msgDiv = document.createElement("div");
                    msgDiv.className = "chat-msg bot";
                    msgDiv.innerHTML = renderMarkdown(data.recipe_markdown);
                    chatBox.appendChild(msgDiv);
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            } catch (err) {
                console.error("AI Generation Error:", err);
            } finally {
                generateBtn.textContent = "🤖 Generate Pure Veg AI Recipe";
                generateBtn.disabled = false;
            }
        });
    }
}

function addIngredient(item) {
    const items = String(item).split(/[,\n;]/).map((v) => v.trim()).filter(Boolean);
    let added = false;
    items.forEach((formatted) => {
        if (!fridgeItems.some((existing) => existing.toLowerCase() === formatted.toLowerCase())) {
            fridgeItems.push(formatted);
            added = true;
        }
    });
    if (added) renderFridgeTags();
}

function removeIngredient(item) {
    fridgeItems = fridgeItems.filter((i) => i !== item);
    renderFridgeTags();
}

function clearFridge() {
    fridgeItems = [];
    renderFridgeTags();
}

function renderFridgeTags() {
    const tray = document.getElementById("fridgeTagsTray");
    const countDisplay = document.getElementById("fridgeCount");
    const matchBtn = document.getElementById("matchRecipesBtn");
    const generateBtn = document.getElementById("generateAIRecipeBtn");

    if (!tray) return;

    if (countDisplay) countDisplay.textContent = fridgeItems.length;
    if (fridgeItems.length === 0) {
        tray.innerHTML = `<div class="empty-fridge-msg"><span>🧊 Your fridge is empty! Add ingredients to get started.</span></div>`;
        if (matchBtn) matchBtn.disabled = true;
        if (generateBtn) generateBtn.disabled = true;
        return;
    }

    if (matchBtn) matchBtn.disabled = false;
    if (generateBtn) generateBtn.disabled = false;

    tray.innerHTML = fridgeItems
        .map(
            (item) =>
                `<span class="fridge-tag-pill">${item} <button class="remove-tag-btn" onclick="removeIngredient('${item}')">&times;</button></span>`
        )
        .join("");
}

function setupIntegratedAIChef() {
    const form = document.getElementById("chefChatForm");
    const input = document.getElementById("chefInput");
    const chatBox = document.getElementById("chefChatBox");
    const promptBtns = document.querySelectorAll(".prompt-btn");
    const sendBtn = form ? form.querySelector("button[type='submit']") : null;

    if (!form || !chatBox) return;

    promptBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            const text = btn.innerText.replace(/^[\u{1F300}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F900}-\u{1F9FF}\s]+/u, "").trim();
            input.value = text;
            input.focus();
        });
    });

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (isSubmittingChef) return;

        const message = input.value.trim();
        if (!message) return;

        isSubmittingChef = true;
        if (sendBtn) sendBtn.disabled = true;

        appendChatMessage("user", message);
        input.value = "";

        const loadingId = appendChatMessage("bot", "<i>CookEase is analyzing your question... 🍳</i>");

        try {
            const response = await fetch("/api/ai-chef/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message }),
            });

            const data = await response.json();
            const loadingElem = document.getElementById(loadingId);

            if (!response.ok) {
                if (loadingElem) loadingElem.innerHTML = `<p style="color:#ef4444;">❌ ${data.error || "CookEase is unavailable."}</p>`;
                return;
            }

            if (loadingElem) loadingElem.innerHTML = renderMarkdown(data.reply);
        } catch (err) {
            const loadingElem = document.getElementById(loadingId);
            if (loadingElem) loadingElem.innerHTML = `<p style="color:#ef4444;">❌ Failed to reach CookEase service.</p>`;
        } finally {
            isSubmittingChef = false;
            if (sendBtn) sendBtn.disabled = false;
        }
    });

    function appendChatMessage(sender, text) {
        const msgDiv = document.createElement("div");
        const id = "msg_" + Date.now();
        msgDiv.id = id;
        msgDiv.className = `chat-msg ${sender}`;
        msgDiv.innerHTML = text;
        chatBox.appendChild(msgDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
        return id;
    }
}

function setupRecipeRoulette() {
    const rouletteNavBtn = document.getElementById("rouletteNavBtn");
    const rouletteModal = document.getElementById("rouletteModal");
    const closeRouletteModal = document.getElementById("closeRouletteModal");
    const spinBtn = document.getElementById("spinWheelBtn");
    const canvas = document.getElementById("rouletteCanvas");
    const resultBox = document.getElementById("rouletteResult");
    const resultTitle = document.getElementById("rouletteResultTitle");
    const resultIcon = document.getElementById("rouletteResultIcon");
    const viewRecipeBtn = document.getElementById("viewRouletteRecipeBtn");

    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    let wheelRecipes = [];
    let currentAngle = 0;
    let selectedRecipe = null;
    const colors = ["#f95700", "#111827", "#f95700", "#111827", "#f95700", "#111827"];

    async function loadWheelRecipes() {
        try {
            const response = await fetch("/api/recipes/search?tag=all");
            if (!response.ok) return;
            const recipes = await response.json();

            if (recipes.length > 0) {
                const shuffled = recipes.sort(() => 0.5 - Math.random());
                wheelRecipes = shuffled.slice(0, 6);
            } else {
                wheelRecipes = [
                    { title: "Dal Palak", key: "", icon: "🍲" },
                    { title: "Paneer Tikka", key: "", icon: "🍢" },
                    { title: "Veg Biryani", key: "", icon: "🍚" },
                    { title: "Aloo Gobi", key: "", icon: "🥘" },
                    { title: "Chana Masala", key: "", icon: "🧆" },
                    { title: "Kadhai Paneer", key: "", icon: "🍛" },
                ];
            }
            drawWheel();
        } catch (err) {
            console.error("Failed to load wheel recipes:", err);
        }
    }

    function drawWheel() {
        if (wheelRecipes.length === 0) return;
        const numSlices = wheelRecipes.length;
        const sliceAngle = (2 * Math.PI) / numSlices;
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const radius = 95;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        for (let i = 0; i < numSlices; i++) {
            const angle = currentAngle + i * sliceAngle;
            ctx.beginPath();
            ctx.fillStyle = colors[i % colors.length];
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius, angle, angle + sliceAngle);
            ctx.fill();

            ctx.save();
            ctx.translate(centerX, centerY);
            ctx.rotate(angle + sliceAngle / 2);
            ctx.textAlign = "right";
            ctx.fillStyle = "#ffffff";
            ctx.font = "bold 10px 'Plus Jakarta Sans', sans-serif";

            let label = wheelRecipes[i].title;
            if (label.length > 12) label = label.substring(0, 11) + "…";
            ctx.fillText(label, radius - 10, 4);
            ctx.restore();
        }

        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
        ctx.lineWidth = 8;
        ctx.strokeStyle = "#111827";
        ctx.stroke();
    }

    if (rouletteNavBtn) {
        rouletteNavBtn.addEventListener("click", (e) => {
            e.preventDefault();
            rouletteModal.classList.add("show");
            resultBox.style.display = "none";
            loadWheelRecipes();
        });
    }

    if (closeRouletteModal) {
        closeRouletteModal.addEventListener("click", () => rouletteModal.classList.remove("show"));
    }

    if (spinBtn) {
        spinBtn.addEventListener("click", async () => {
            if (wheelRecipes.length === 0) await loadWheelRecipes();
            spinBtn.disabled = true;
            spinBtn.textContent = "🔄 Spinning...";
            resultBox.style.display = "none";

            const winningIndex = Math.floor(Math.random() * wheelRecipes.length);
            selectedRecipe = wheelRecipes[winningIndex];

            const sliceAngle = (2 * Math.PI) / wheelRecipes.length;
            const targetRotation = 8 * Math.PI + (wheelRecipes.length - winningIndex - 0.5) * sliceAngle - Math.PI / 2;

            let start = null;
            const duration = 3500;

            function animate(timestamp) {
                if (!start) start = timestamp;
                const progress = (timestamp - start) / duration;

                if (progress < 1) {
                    const easeOut = 1 - Math.pow(1 - progress, 3);
                    currentAngle = easeOut * targetRotation;
                    drawWheel();
                    requestAnimationFrame(animate);
                } else {
                    currentAngle = targetRotation;
                    drawWheel();
                    resultIcon.textContent = selectedRecipe.icon || "🌱";
                    resultTitle.textContent = selectedRecipe.title;
                    resultBox.style.display = "block";
                    spinBtn.disabled = false;
                    spinBtn.innerHTML = "🎲 Spin Again!";
                }
            }
            requestAnimationFrame(animate);
        });
    }

    if (viewRecipeBtn) {
        viewRecipeBtn.addEventListener("click", () => {
            if (selectedRecipe && selectedRecipe.key) {
                loadRecipeDetails(selectedRecipe.key);
                rouletteModal.classList.remove("show");
            }
        });
    }
}

function setupMobileDrawer() {
    const menuToggle = document.getElementById("menuToggle");
    const sidebar = document.getElementById("sidebar");
    const closeSidebarBtn = document.getElementById("closeSidebarBtn");
    const overlay = document.getElementById("sidebarOverlay");
    const backBtn = document.getElementById("backBtn");
    const detailDrawer = document.getElementById("detailDrawer");
    const shareBtn = document.getElementById("shareBtn");
    const favBtn = document.getElementById("favBtn");

    if (menuToggle)
        menuToggle.addEventListener("click", () => {
            if (sidebar) sidebar.classList.add("show");
            if (overlay) overlay.classList.add("show");
        });

    if (closeSidebarBtn)
        closeSidebarBtn.addEventListener("click", () => {
            if (sidebar) sidebar.classList.remove("show");
            if (overlay) overlay.classList.remove("show");
        });

    if (overlay)
        overlay.addEventListener("click", () => {
            if (sidebar) sidebar.classList.remove("show");
            if (detailDrawer) detailDrawer.classList.remove("show");
            overlay.classList.remove("show");
        });

    if (backBtn && detailDrawer) {
        backBtn.addEventListener("click", () => {
            if (detailDrawer.classList.contains("maximized")) {
                detailDrawer.classList.remove("maximized");
                backBtn.innerHTML = "←";
            } else {
                detailDrawer.classList.remove("show");
                if (overlay) overlay.classList.remove("show");
            }
        });

        backBtn.addEventListener("dblclick", () => {
            detailDrawer.classList.toggle("maximized");
            if (detailDrawer.classList.contains("maximized")) {
                backBtn.innerHTML = "🗗";
            } else {
                backBtn.innerHTML = "←";
            }
        });
    }

    if (shareBtn) {
        shareBtn.addEventListener("click", () => {
            if (currentRecipeKey) {
                const shareUrl = window.location.origin + "/#recipe=" + currentRecipeKey;
                if (navigator.clipboard) {
                    navigator.clipboard.writeText(shareUrl);
                    alert("📋 Recipe link copied to clipboard!");
                } else {
                    prompt("Copy recipe link:", shareUrl);
                }
            } else {
                alert("No recipe selected to share.");
            }
        });
    }

    if (favBtn) {
        favBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const key = favBtn.getAttribute("data-key") || currentRecipeKey;
            if (!key) return;
            await toggleFavoriteAPI(key);
        });
    }
}

function handleUrlRecipeHash() {
    const hash = window.location.hash;
    if (hash && hash.includes("#recipe=")) {
        const key = hash.replace("#recipe=", "").trim();
        if (key) {
            setTimeout(() => {
                loadRecipeDetails(key);
            }, 600);
        }
    }
}

async function checkCurrentUser() {
    try {
        const res = await fetch("/api/auth/me");
        const data = await res.json();

        const userNameDisplay = document.getElementById("userNameDisplay");
        const logoutBtn = document.getElementById("logoutBtn");
        const avatarBtn = document.getElementById("avatarBtn");

        if (data.logged_in) {
            userNameDisplay.textContent = `Hi, ${data.user.username}`;
            logoutBtn.style.display = "inline-block";
            avatarBtn.style.cursor = "default";
            loadMySubmissionsTracker();
        } else {
            userNameDisplay.textContent = "";
            logoutBtn.style.display = "none";
            avatarBtn.style.cursor = "pointer";
        }
    } catch (err) {
        console.error("Failed to check auth status:", err);
    }
}

function setupAuthModal() {
    const avatarBtn = document.getElementById("avatarBtn");
    const authModal = document.getElementById("authModal");
    const closeAuthModal = document.getElementById("closeAuthModal");
    const loginTabBtn = document.getElementById("loginTabBtn");
    const signupTabBtn = document.getElementById("signupTabBtn");
    const loginForm = document.getElementById("loginForm");
    const signupForm = document.getElementById("signupForm");
    const logoutBtn = document.getElementById("logoutBtn");

    avatarBtn.addEventListener("click", async () => {
        const res = await fetch("/api/auth/me");
        const data = await res.json();
        if (!data.logged_in) authModal.classList.add("show");
    });

    closeAuthModal.addEventListener("click", () =>
        authModal.classList.remove("show")
    );

    loginTabBtn.addEventListener("click", () => {
        loginTabBtn.classList.add("active");
        signupTabBtn.classList.remove("active");
        loginForm.classList.add("active");
        signupForm.classList.remove("active");
    });

    signupTabBtn.addEventListener("click", () => {
        signupTabBtn.classList.add("active");
        loginTabBtn.classList.remove("active");
        signupForm.classList.add("active");
        loginForm.classList.remove("active");
    });

    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("loginEmail").value;
        const password = document.getElementById("loginPassword").value;
        const errDiv = document.getElementById("loginError");
        errDiv.textContent = "";

        try {
            const res = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                errDiv.textContent = data.error || "Login failed";
                return;
            }
            authModal.classList.remove("show");
            checkCurrentUser();
            fetchRecipes();
        } catch (err) {
            errDiv.textContent = "Server error. Try again.";
        }
    });

    signupForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const username = document.getElementById("signupUsername").value;
        const email = document.getElementById("signupEmail").value;
        const password = document.getElementById("signupPassword").value;
        const errDiv = document.getElementById("signupError");
        errDiv.textContent = "";

        try {
            const res = await fetch("/api/auth/signup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, email, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                errDiv.textContent = data.error || "Signup failed";
                return;
            }
            authModal.classList.remove("show");
            checkCurrentUser();
            fetchRecipes();
        } catch (err) {
            errDiv.textContent = "Server error. Try again.";
        }
    });

    logoutBtn.addEventListener("click", async () => {
        await fetch("/api/auth/logout", { method: "POST" });
        checkCurrentUser();
        fetchRecipes();
    });
}

async function fetchTodaysPick() {
    try {
        const response = await fetch("/api/recipes/todays-pick");
        if (!response.ok) return;
        const pick = await response.json();
        const pickCard = document.getElementById("pickCard");
        if (!pickCard) return;

        pickCard.setAttribute("onclick", `loadRecipeDetails('${pick.key}')`);
        const plate = pickCard.querySelector(".pick-plate");
        if (plate) {
            plate.innerHTML = pick.image
                ? `<img src="${pick.image}" alt="${pick.title}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;" onerror="this.outerHTML='${pick.icon}'">`
                : pick.icon;
        }
        const info = pickCard.querySelector(".pick-info");
        if (info)
            info.innerHTML = `<h3>${pick.title}</h3><div class="kcal"><b>${pick.kcal}</b> kcal</div>`;
        const saveBtn = pickCard.querySelector(".save-btn");
        if (saveBtn) saveBtn.setAttribute("data-key", pick.key);
    } catch (err) {
        console.error("Failed to fetch today's pick:", err);
    }
}

function setupGlobalFavoriteListener() {
    document.addEventListener("click", async (e) => {
        const btn = e.target.closest(".save-btn");
        if (!btn || btn.closest(".detail-card") || btn.id === "favBtn") return;
        e.stopPropagation();
        e.preventDefault();
        const key = btn.getAttribute("data-key");
        if (!key) return;
        await toggleFavoriteAPI(key);
    });
}

async function toggleFavoriteAPI(key) {
    try {
        const response = await fetch(`/api/favorites/${key}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });
        if (!response.ok) return;
        const data = await response.json();
        const isFav = data.favorited;
        const matchingButtons = document.querySelectorAll(
            `[data-key="${key}"], .detail-card .save-btn, #favBtn`
        );
        matchingButtons.forEach((b) => {
            if (isFav) {
                b.classList.add("active");
                b.innerHTML = "❤️";
            } else {
                b.classList.remove("active");
                b.innerHTML = "🤍";
            }
        });
        if (currentTag === "favorites") await fetchRecipes();
    } catch (err) {
        console.error("Failed to toggle favorite:", err);
    }
}

async function fetchRecipes() {
    try {
        const url = `/api/recipes/search?q=${encodeURIComponent(
            searchQuery
        )}&tag=${encodeURIComponent(currentTag)}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error("Network error");
        allFetchedRecipes = await response.json();
        renderPopularRecipes();
        
        if (allFetchedRecipes.length > 0 && !currentRecipeKey && !window.location.hash.includes("#recipe=")) {
            loadRecipeDetails(allFetchedRecipes[0].key);
        } else if (allFetchedRecipes.length === 0) {
            clearRecipeDetails();
        }
    } catch (error) {
        console.error("Search failed:", error);
    }
}

function renderPopularRecipes() {
    const container = document.getElementById("popularGrid");
    if (!container) return;
    if (allFetchedRecipes.length === 0) {
        container.innerHTML = `<div class="no-results show" style="padding: 20px; color: #888;">No recipes found for this section.</div>`;
        return;
    }
    const recipesToDisplay = isExpanded
        ? allFetchedRecipes
        : allFetchedRecipes.slice(0, INITIAL_LIMIT);
    container.innerHTML = recipesToDisplay
        .map((recipe) => {
            const imageHTML = recipe.image
                ? `<img src="${recipe.image}" alt="${recipe.title}" style="width:100%; height:100%; object-fit:cover; border-radius:8px;" onerror="this.style.display='none'; this.nextElementSibling.style.display='block';"><span class="placeholder-icon" style="display:none;">${
                      recipe.icon || "🌱"
                  }</span>`
                : `<span class="placeholder-icon">${
                      recipe.icon || "🌱"
                  }</span>`;
            return `
            <div class="recipe-card" onclick="loadRecipeDetails('${
                recipe.key
            }')">
                <button class="circle-btn save-btn ${
                    recipe.favorited ? "active" : ""
                }" data-key="${recipe.key}" aria-label="Save Favorite">
                    ${recipe.favorited ? "❤️" : "🤍"}
                </button>
                <div class="recipe-img-placeholder">${imageHTML}</div>
                <div class="recipe-info">
                    <h4>${recipe.title}</h4>
                    <div class="recipe-meta"><span>⏱️ ${
                        recipe.time || "30m"
                    }</span><span>🔥 ${
                recipe.kcal || "350"
            } kcal</span></div>
                </div>
            </div>`;
        })
        .join("");
    updateViewAllButtonText();
}

function setupViewAllButton() {
    const viewAllBtn = document.getElementById("viewAll");
    if (!viewAllBtn) return;
    viewAllBtn.addEventListener("click", (e) => {
        e.preventDefault();
        isExpanded = !isExpanded;
        renderPopularRecipes();
    });
}

function updateViewAllButtonText() {
    const viewAllBtn = document.getElementById("viewAll");
    if (!viewAllBtn) return;
    if (allFetchedRecipes.length <= INITIAL_LIMIT)
        viewAllBtn.style.display = "none";
    else {
        viewAllBtn.style.display = "inline-block";
        viewAllBtn.textContent = isExpanded ? "View less" : "View all";
    }
}

async function loadRecipeDetails(key) {
    currentRecipeKey = key;
    try {
        const response = await fetch(`/api/recipes/${key}`);
        if (!response.ok) return;
        const recipe = await response.json();
        syncDetailSaveButton(recipe.favorited, recipe.key);

        const photoBox = document.querySelector(".detail-photo");
        
        let imageUrl = recipe.image || recipe.image_url;
        if (!imageUrl || imageUrl.trim() === "") {
            imageUrl = "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=800&q=80";
        }
        
        if (photoBox) {
            photoBox.innerHTML = `<img src="${imageUrl}" alt="${recipe.title}" style="width:100%; height:100%; object-fit:cover;" onerror="this.src='https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=800&q=80'">`;
        }

        const titleElem = document.querySelector(".detail-card h3");
        if (titleElem) titleElem.textContent = recipe.title;

        const descElem = document.querySelector(".detail-card p.desc");
        if (descElem)
            descElem.textContent = recipe.desc || "Classic homemade recipe.";

        const nutri = recipe.nutrition || {};
        const nutriVals = document.querySelectorAll(".nutri-item .val");
        if (nutriVals.length >= 4) {
            nutriVals[0].textContent = nutri.calories || (recipe.kcal ? `${recipe.kcal} kcal` : "350 kcal");
            nutriVals[1].textContent = nutri.carbs || "25g";
            nutriVals[2].textContent = nutri.protein || "8g";
            nutriVals[3].textContent = nutri.fat || "12g";
        }

        let dynamicContent = document.getElementById("dynamicRecipeContent");
        const ingredientsHTML =
            recipe.ingredients && recipe.ingredients.length > 0
                ? recipe.ingredients
                      .map(
                          (ing) => `<div class="ingredient"><div class="left"><div class="ico">${
                              ing.icon || "🥦"
                          }</div><span>${ing.name} ${ing.quantity ? '(' + ing.quantity + ')' : ''}</span></div></div>`
                      )
                      .join("")
                : `<p style="color:#888; font-size:13px;">No ingredients listed.</p>`;
        
        const instructionsHTML =
            recipe.instructions && recipe.instructions.length > 0
                ? recipe.instructions
                      .map(
                          (step, idx) =>
                              `<div class="instruction-step"><span class="step-num">${
                                  idx + 1
                              }.</span><p class="step-text">${step}</p></div>`
                      )
                      .join("")
                : `<p style="color:#888; font-size:13px;">No instructions provided.</p>`;

        if (dynamicContent)
            dynamicContent.innerHTML = `<div class="ingredients-label" style="margin-top:20px; margin-bottom:8px; font-weight:bold;">Ingredients</div><div class="ingredients-wrap">${ingredientsHTML}</div><div class="ingredients-label" style="margin-top:20px; margin-bottom:8px; font-weight:bold;">Cooking Instructions</div><div class="instructions-wrap">${instructionsHTML}</div>`;

        if (window.innerWidth <= 992) {
            const detailDrawer = document.getElementById("detailDrawer");
            const overlay = document.getElementById("sidebarOverlay");
            if (detailDrawer) detailDrawer.classList.add("show");
            if (overlay) overlay.classList.add("show");
        }
    } catch (err) {
        console.error("Error loading recipe detail:", err);
    }
}

function syncDetailSaveButton(isFavorited, key) {
    const detailSaveBtn = document.getElementById("favBtn") || document.querySelector(".detail-card .circle-btn.save-btn");
    if (detailSaveBtn) {
        detailSaveBtn.setAttribute("data-key", key);
        if (isFavorited) {
            detailSaveBtn.classList.add("active");
            detailSaveBtn.innerHTML = "❤️";
        } else {
            detailSaveBtn.classList.remove("active");
            detailSaveBtn.innerHTML = "🤍";
        }
    }
}

function clearRecipeDetails() {
    currentRecipeKey = null;
    const titleElem = document.querySelector(".detail-card h3");
    if (titleElem) titleElem.textContent = "No Recipe Selected";
    const descElem = document.querySelector(".detail-card p.desc");
    if (descElem)
        descElem.textContent = "Search or select a recipe from the list.";
    const nutVals = document.querySelectorAll(".nutri-item .val");
    nutVals.forEach((v) => (v.textContent = "-"));
    const dynamicContent = document.getElementById("dynamicRecipeContent");
    if (dynamicContent) dynamicContent.innerHTML = "";
    syncDetailSaveButton(false, "");
}

function setupSearchBar() {
    const searchInput = document.getElementById("searchInput");
    if (searchInput) {
        let timeout = null;
        searchInput.addEventListener("input", (e) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => {
                searchQuery = e.target.value.trim();
                fetchRecipes();
            }, 300);
        });
    }
}