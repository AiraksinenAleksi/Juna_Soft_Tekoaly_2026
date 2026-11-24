let stationMap = {};
let loading = false;

async function loadStationMetadata() {
    try {
        const response = await fetch("/api/stations");

        if (!response.ok) return;

        const stations = await response.json();

        stationMap = Object.fromEntries(
            stations.map(s => [s.code, s.name])
        );
    } catch {
        console.warn("Asemien metatietoja ei saatu ladattua.");
    }
}

async function loadDepartures() {
    if (loading) return;

    loading = true;

    const station = document.getElementById("station").value;
    const list = document.getElementById("departure-list");
    const status = document.getElementById("status");

    document.getElementById("station-name").textContent =
        stationMap[station] || station;

    status.textContent = "Haetaan junatietoja...";

    try {
        const response = await fetch(
            `/api/departures?station=${encodeURIComponent(station)}`
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error);
        }

        list.replaceChildren();

        if (!data.departures.length) {
            const row = list.insertRow();
            const cell = row.insertCell();

            cell.colSpan = 5;
            cell.className = "no-data";
            cell.textContent = "Ei lähteviä junia tällä hetkellä.";
        }

        data.departures.forEach(train => {
            const row = list.insertRow();

            const number = row.insertCell();
            number.className = "train-number";
            number.textContent = train.train_number ?? "—";

            const destination = row.insertCell();
            destination.textContent =
                stationMap[train.destination] ||
                train.destination ||
                "Ei tiedossa";

            row.insertCell().textContent =
                train.scheduled_time || "—";

            const estimated = row.insertCell();

            estimated.textContent = train.estimated_time
                ? `${train.estimated_time} (${train.time_status})`
                : "Ei arviota";

            const delay = row.insertCell();

            if (train.delay_minutes === null) {
                delay.textContent = "—";
            } else if (train.delay_minutes > 0) {
                delay.textContent =
                    `${train.delay_minutes} min myöhässä`;
                delay.className = "delay";
            } else if (train.delay_minutes < 0) {
                delay.textContent =
                    `${Math.abs(train.delay_minutes)} min etuajassa`;
                delay.className = "on-time";
            } else {
                delay.textContent = "Aikataulussa";
                delay.className = "on-time";
            }
        });

        status.textContent = "Tiedot päivitetty.";

        document.getElementById("last-update").textContent =
            "Päivitetty " +
            new Date().toLocaleTimeString("fi-FI", {
                timeZone: "Europe/Helsinki"
            });

    } catch (error) {
        list.replaceChildren();

        const row = list.insertRow();
        const cell = row.insertCell();

        cell.colSpan = 5;
        cell.className = "no-data";
        cell.textContent =
            "Junatietoja ei tällä hetkellä saada haettua.";

        status.textContent = "Tietojen haku epäonnistui.";
        console.error(error);

    } finally {
        loading = false;
    }
}

function updateClock() {
    document.getElementById("current-time").textContent =
        new Date().toLocaleTimeString("fi-FI", {
            timeZone: "Europe/Helsinki"
        });
}

async function initializeApp() {
    await loadStationMetadata();
    await loadDepartures();
}

document.getElementById("station").addEventListener(
    "change", loadDepartures
);

document.getElementById("refresh-button").addEventListener(
    "click", loadDepartures
);

updateClock();
setInterval(updateClock, 1000);
initializeApp();
setInterval(loadDepartures, 30000);
