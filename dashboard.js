async function loadDashboard() {
    const token = localStorage.getItem("token");
    if (!token) {
        window.location.href = "login.html";
        return;
    }

    try {
        const res = await fetch("http://127.0.0.1:8000/me", {
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        // If the token is invalid or expired, the server should return a non-ok status.
        if (!res.ok) {
            // Clear the bad token and redirect to login
            localStorage.removeItem("token");
            window.location.href = "login.html";
            return;
        }

        const data = await res.json();
        if (!data.user) {
            console.error("User data not found in response.");
            return;
        }

        const user = data.user;

        document.getElementById("welcomeUser").textContent = `Welcome back, ${user.username}!`;
        document.getElementById("xpValue").textContent = user.xp;
        document.getElementById("quizCount").textContent = user.quizzes_taken;
        document.getElementById("accuracyValue").textContent = (user.accuracy * 10).toFixed(1) + "%";
        document.getElementById("streakValue").textContent = user.streak + " days";
    } catch (error) {
        console.error("Failed to load dashboard data:", error);
        // Optionally, display an error message to the user on the page
    }
}

loadDashboard();