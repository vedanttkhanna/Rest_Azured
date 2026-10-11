import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  Check,
  Info,
  MapPin,
  Search,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { createJob, getLocalHealth } from "../api/client";
import type { LocationInput } from "../api/types";
import { MapView, type Point } from "../components/MapView";
import { ErrorPanel, PageHeading } from "../components/ui";
import { inServiceArea } from "../lib/geo";
import { sampleLocation } from "../mocks/fixtures";
import { useAuth } from "../auth/Auth";

export default function NewAssessment() {
  const auth = useAuth();
  const health = useQuery({ queryKey: ["local-health"], queryFn: getLocalHealth, enabled: auth.local });
  const addressAvailable = !auth.local || health.data?.geocoding === true;
  const [mode, setMode] = useState<"pin" | "address">("pin");
  const [point, setPoint] = useState<Point>({
    lat: sampleLocation.lat,
    lng: sampleLocation.lng,
  });
  const [lat, setLat] = useState(String(point.lat));
  const [lng, setLng] = useState(String(point.lng));
  const [address, setAddress] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [validation, setValidation] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: createJob,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      navigate(`/jobs/${result.job_id}`);
    },
  });
  const select = (value: Point) => {
    setPoint(value);
    setLat(value.lat.toFixed(7));
    setLng(value.lng.toFixed(7));
    setConfirmed(false);
    setValidation("");
  };
  const updateCoordinate = (key: "lat" | "lng", value: string) => {
    if (key === "lat") setLat(value);
    else setLng(value);
    setConfirmed(false);
    const currentLat = Number(key === "lat" ? value : lat),
      currentLng = Number(key === "lng" ? value : lng);
    if (value.trim() && inServiceArea(currentLat, currentLng))
      setPoint({ lat: currentLat, lng: currentLng });
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setValidation("");
    let input: LocationInput;
    if (mode === "pin") {
      if (
        !lat.trim() ||
        !lng.trim() ||
        !inServiceArea(Number(lat), Number(lng))
      ) {
        setValidation(
          "Choose a rooftop inside Delhi/NCR: latitude 28.4–28.9, longitude 76.8–77.4.",
        );
        return;
      }
      if (!confirmed) {
        setValidation(
          "Confirm that the pin is on the roof you want to assess.",
        );
        return;
      }
      input = {
        lat: Number(lat),
        lng: Number(lng),
        ...(address.trim() ? { address: address.trim() } : {}),
      };
    } else {
      if (!address.trim()) {
        setValidation("Enter a Delhi/NCR address.");
        return;
      }
      input = { address: address.trim() };
    }
    mutation.mutate(input);
  };
  return (
    <div className="page-enter">
      <PageHeading
        eyebrow="LET’S FIND YOUR SUNSHINE"
        title="Which rooftop is yours?"
        description="A good assessment starts with the right building."
      />
      <div className="assessment-grid">
        <section className="assessment-map-card">
          <MapView
            selectable
            point={point}
            onSelect={select}
            sample={auth.demo}
          />
          <div className="map-help">
            <MapPin size={19} />
            <div>
              <strong>Place the pin on the center of your roof.</strong>
              <span>
                Zoom in, click the rooftop, or drag the pin. Enter coordinates
                to move to another building anywhere in Delhi/NCR.
              </span>
            </div>
          </div>
        </section>
        <form className="assessment-form card" onSubmit={submit}>
          <div className="card-heading">
            <span className="icon-tile">
              <Sun size={22} />
            </span>
            <div>
              <h2>Your rooftop details</h2>
              <p>Delhi & NCR service area</p>
            </div>
          </div>
          <div className="segmented-control">
            <button
              type="button"
              className={mode === "pin" ? "active" : ""}
              onClick={() => {
                setMode("pin");
                setValidation("");
              }}
            >
              <MapPin size={15} /> Map pin
            </button>
            <button
              type="button"
              className={mode === "address" ? "active" : ""}
              disabled={!addressAvailable}
              onClick={() => {
                setMode("address");
                setValidation("");
              }}
            >
              <Search size={15} /> Address
            </button>
          </div>
          {auth.local && !addressAvailable && (
            <div className="info-note"><Info size={17} /><p>Choose a map pin or enter coordinates. Address lookup becomes available when AWS credentials are configured on this Mac.</p></div>
          )}
          {auth.local && health.error && <ErrorPanel error="The local model API is unavailable. Restart with npm run dev." />}
          <label className="field-label" htmlFor="address">
            {mode === "pin"
              ? "Rooftop name or address (optional)"
              : "Full address"}
          </label>
          <input
            id="address"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="e.g. Sector 6, Dwarka, New Delhi"
            autoComplete="street-address"
            maxLength={500}
          />
          {mode === "pin" ? (
            <>
              <div className="coordinate-fields">
                <div>
                  <label className="field-label" htmlFor="lat">
                    Latitude
                  </label>
                  <input
                    id="lat"
                    inputMode="decimal"
                    value={lat}
                    onChange={(event) =>
                      updateCoordinate("lat", event.target.value)
                    }
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="lng">
                    Longitude
                  </label>
                  <input
                    id="lng"
                    inputMode="decimal"
                    value={lng}
                    onChange={(event) =>
                      updateCoordinate("lng", event.target.value)
                    }
                  />
                </div>
              </div>
              <label className="confirm-roof">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>I’ve checked the pin is on the correct rooftop.</span>
              </label>
            </>
          ) : (
            <div className="info-note">
              <Info size={17} />
              <p>
                Address lookup can select a neighboring building. Use the map
                pin for an exact roof location.
              </p>
            </div>
          )}
          {validation && (
            <p className="inline-error" role="alert">
              {validation}
            </p>
          )}
          {mutation.error && <ErrorPanel error={mutation.error} />}
          <button
            className="button full"
            disabled={mutation.isPending}
            type="submit"
          >
            {mutation.isPending
              ? "Starting assessment…"
              : "Find my solar potential"}
            <ArrowUpRight size={18} />
          </button>
          <div className="assessment-expect">
            <ShieldCheck size={16} />
            <p>
              {auth.demo
                ? "Demo mode reuses the sample building and makes no AWS requests."
                : auth.local
                  ? "Runs your trained model on this rooftop. Fresh imagery, building footprints, and weather can take up to 2 minutes to fetch."
                  : "Usually 15–25 seconds. The first assessment after a quiet period can take around 2 minutes."}
            </p>
          </div>
          <div className="included">
            <span>
              <Check size={14} /> Panel layout
            </span>
            <span>
              <Check size={14} /> Energy & savings
            </span>
            <span>
              <Check size={14} /> Shade analysis
            </span>
          </div>
        </form>
      </div>
      <div className="soft-note">
        <Info size={17} />
        <p>
          Satellite-based estimates help you explore options. A site survey can
          confirm roof condition, structure, and equipment missed in imagery.
        </p>
      </div>
    </div>
  );
}
