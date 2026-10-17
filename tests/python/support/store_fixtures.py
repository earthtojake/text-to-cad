"""Store fixtures for tests: build a tree and lay a view of it, or seed a
document's result straight into the store without a kernel."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping


def build_view(
    compound: Any,
    *,
    package_dir: Path,
    root_name: str,
    force: bool = False,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Build ``compound``'s tree into the store and lay a view of it at
    ``package_dir`` (the directory shape the older readers consume). Returns the
    build stats plus the tree hash under ``tree``."""
    from cadgen.store.build import build_tree_from_compound
    from cadgen.store.view import export_view

    tree_hash, _tree, stats = build_tree_from_compound(
        compound,
        root_name=root_name,
        force=force,
        progress=progress,
    )
    export_view(tree_hash, Path(package_dir))
    result = dict(stats)
    result["tree"] = tree_hash
    return result


# Proven small box inputs, and each one's part as cadgen derives it under the named
# producer: its display mesh (``glb``) and selector table (``selectors``), zlib-compressed --
# what ``cadgen.store.parts`` derives from ``payload`` under FIXTURE_PRODUCER
# (test_store_seed_inputs.py holds them to it). Keeping encoded inputs here lets catalog and
# security fixtures seed genuine geometry and display data without importing OCP in the process
# under test. A new PART_VERSION, or another producer, names another part: derive them again.
FIXTURE_PRODUCER = {'build123d': '0.11.1', 'ocp': '7.9.3.1', 'cadqueryOcp': '7.9.3.1.1'}
_GEOMETRY_FIXTURES = [{'kind': 'native', 'codec': 'bintools-v4', 'brep': '0bdb4f63f3ab902a54be4da365fe1810a2cf9fb9f688d452e8a608a8c4328f51', 'faceColors': {}, 'contentHash': 'df0a0992298bdf82f83ba62f12a0286b49b4736399da4818bce4a41ab2a1eaef', 'payload': 'eJylVttu00AQXTvXuumFFih3DE8Q8QBpxCN1lSLxgFSkRLxbaRsqRXGUEKTyxHfwE/wAUvsX/EbEFzBOdmYTeyZrB6uKVzuzc87MnB3XOx2eD/zWcbt1fPLe70TDqB/1rvzPzVf+i+5Lf24Nx93w7Nz7GHXDr5fRYOy/9lqT0bfzxtnYbzQ9R7HP9AhXWR2qgeB4LUQwkZION+tyECHyc7BBoCF/HcwJG4ebdTlIzxocsjpkr0PuUtsjBP/NIRVhdkfG/puGdEOys1MJMj+SWAKZ3Aj0SAhS20WE5AFrDrSBjnkR6JEQ5IjJAJY+2A8EeRECG8KnqH/ViwaHJzCF9fp00BldhoPepE/zuT0ZXYRdUN9bm/jSCNn8pte4yi2l1QC5u5A9kETIdntSB/IC5x4AUiCJkHUoC4EsfqbJKYV5nfaXcAgKO2x6lQ+/fv/8++f7Oz5q3ChHOfBXt3jOU5l5ltHTmW3wcV1HSfoDowsvdxWj+PBz3Hum3yLHIJXNEkceSQVuQeQIxiL8FgQjcXyKW0jWxlEpniOPBKUqiRzBWIZXUTCmOT5GjkvI/HkoQEVEBmMVfkuCkZAR0HSwNE9eOb7ecZ6gzyNcPETnoiKeFNyZK+4B+iTKzX3TeIFzF5JrDJ8k1H4DXmXJ6KkMAr+Hewe2bIJUNksceRrQpU2RIxhrKoPA7+AWkrVxjB+OY4UFglJtiRzBuK0yCJw47iPHJeSqkKO7IyKDcVdlEDgCmg6SwO/qHec2+uzh4hY6G4EbGlrgu2wqGyyf6ZEbh+T1BsY9MZW4eToVzMDc1SVkTwq+vwo5zp2X2AIyXQOaoVTEbb1D1VRbuPDR2RTR0NBFrLGpbEpsYx3xYgNjzMBaRNIDP2prwnn3YBVyXB9rEekO4LQ3RcTWOSRAkhHO3IUiGhq6iHh9TEAc0EYUqGiFDVsIaIqmA6LWTUD8Bhh906XBfi8ENLXQAZFyvYAB76PHDnpS03EOmcGO8eou/jeDQqrT9+8fa241eQ==', 'glb': 'eNq1Vktv2kAQXvIOSdu0TdOeqmhPPTjIL2yTS0lpK6VKIEqiXCIOi71OrYIdmSUPRUj8s177szprr2ExhNBIRfLufOOZb2ZndoCr9vn3BYTQpyJCX5cR+nHWqD9g0u1Shvcf8A2Nu0EU4n2sl1Ss4Csa0piwKAaNSzyAuK9gesdi0uX2QgfSNYkZd6Mty1R933EpcVzDs1xTtWxDN4lJDIN6Ttk2PM9vuUbF1twWNctOWbUch/ie6zi+vXej8bitqBd6SYROAPSXaklVxNNUcIfcgU4DDFkqBuggKZ+4tBa1oxjcLsGIQma1Nj8ZV+AwCikQ+5SwXswlRkJInYHUpaQDm0fFaWmWAInvQQTPYxIGftT2APXCX2F0G+JmGjHJsdXzfRpfBPQW7xsKdsEXamH10yQmTMyhiaYLm5MoCNmEYXloqJv9Pph2XcgQ76tC4gd7gPy8RIIqNJUhgsrR7s/ENo4YYUlXL/fUkq3aGrTE0TTHKpu2pYxqm3/V5HFIm6YNUDVFWpNgPISIdh0HnYAFNwISxuKg1WPp6U8aZ4fnh416kk69cXp8cASHhwMFoRckRdSBDDKH4vQTZuKCups2c7woKi9K5xraGbLz+2twKWu6JVUKWpuo8cW3mgEdm/cGjYfR/i1M3l2f5j66G4Y1dD+rHRwdnGJ+6BGBfOzkyK17Rhu+n4ypgEc0vGLQYd1x+G2Or/g7w6xY+iiZCd/E+NneZbguY962Pu5szHC2zFzoCpCFpEOH3y2ldKJmcNimOc6hVfQ8STpzM0gqhjWlBpMkYihHnRFdkcPrOr+wu7t/lhD6clhH0z/VaibIylQ/+DxSZfJQX5X0VYknZ5+PJfPIcWXOiRym8E/4okd4crHyOcj8g9+cQPDMI2dxB/PJc/Nm8uAZMQY5/1kyeqR+U+UC4r/OBbQI+zJaQiuwrqBVtIHW0DqsRdhfoRdoE9ZN9BK9RVvoNaxvYH+P3qFtWLfRDjCknxWxLwg5w4vwbEoYri9wjDD8NUAfJMz3jxIuSLwFsS9IeFFwZnhJ+GaY869JmL8rSnhV5JdhbvtSwuvwbEm4KPLP8AY82xLmXDsSfmJOp9znx+Z37nlBT8zFI/P+1Nz9n++Bv2Uq8sU=', 'selectors': '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'}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '92e6935c58872e596eeda474ad1f8e7dcc4d0c75f4ad9565e332ffc38683671f', 'faceColors': {}, 'contentHash': 'd0a73c5078a3634e889f05f9614b6fdbe678ea9f6f4702e98cb6aafd05741fae', 'payload': 'eJylVstu00AUHTvPuumDFihvDCuIWEAasQRXKRILpCIlYm+laagUxVFCkMqK7+An+AGk8hf8RsUXcJ34zMT23My4WFE8mrlzzrl3ztzEO5kMxn7nqNs5On7n96JJNIqGF/6n9gv/Wf+5v1wNZ/3wdOB9iPrhl/NoPPNfep359OugdTrzW23PEdrn6i1GtgH1gAm8ZBAUUjbg93U1sBTFNRgpAibAXAcuoHgdOA3ccw0NtgH2dSheaiNC8N8acgiLOzLzX7W4G2KvTmTEfM9yMWIKM8iHZTAg5xkyG8w5BJl3UQb5sAwsYhbAcA7mDRlp1ht4ho/R6GIYjQ+PqQsn45Nxb3oejofzkezP3fn0LOyT+16bzJdnsIu7usSosJXWExQ+BXsgTpDp9uQ2FCUu3AA4IE6QsSkzQIY4dcg5h3m97udwQg47bHu19z9//fj759sbPWp8UI5w6NM0RC5TWURWEeksJvS4riM4/9GiSy93naJ481PMPUnerMYgl01Ko55JBG6J1UiLZfouMYtS42NMQaxJoxB6jXomKlWF1UiLVXqVmcW8xofQmGLW76cC1FhmWqzTd4VZlMwgVCdYWSYvHD+ZcR4h5gEG9xFcFlKnBHeWjruHmGy5g7SWNQbPRC7ANQejT5Jqv0GvKrfoCQuD38HcgSmbIJdNSqNeBp3SJquRFhvCwuC3MAWxJo3xo9NY0xJRqbZYjbS4LSwMLjXuQ2OKuc7k6O6wzLS4KywMDkJ1gtLgt5MZ5yZi9jC4gWBlcCUjMfiuNpUNTm0Myba5PZtUkIG6qylmjwPfX8cc5260mLwGsofKIm4nM7KaYgsDH8GqiEpGUsSGNpVNTm3sI7Ybxgrs/aBvtQ3tdgI/WMcc18f+nqLbqyLi6BxpQGkj9NyVIioZSRFxfRQgGrQyBRwtcGArgKpoCSC8rgDxG6D8LS8NznsFUNUiAYTkZgmAdxGxg0h56OhDqrEDr+ni3wyM1JS/f/8AfxceIg==', 'glb': 'eNq1Vltv2jAUNr2Xdlu3dd2epspPe0hR7gReRsc2qVMLVVv1peLBJA6LBgkKoRdVSPyzve5n7ThxwIRLWaUh2T6ffc53LvZJ22pffV9BCH3KI/R1HaEfl/XaIya9Ho1w+RHf0rDnBT4uY7UgYwm3qE9DEgUh7NjEAYgHEqb3UUh6TJ/vgdQlITBg3TAs4liy0rSprri6Yjmy6RBCZKuo6yp1iFEq2aaiFi3ZNh3qkmaJmo5adDVbNprG0a3C/DaDvu/EHjoe0N/IBVnioyHhDrmHPYhQYkODPQjKJTatBu0gBLMbUKIQWbXNMmMb2A98CsQuJVE/ZFJEfAg9AqlHSQcWh/JsaRoACR9ABMsz4ntu0HYA9f1ffnDn40biMY6x2XddGl579A6XNQnbYAu1MAdJEFMq+khFUbnOeeD50ZSiMVJU9cEAVHs2RIjLMpdYYo8QnxNLUIWGNEJQOdr7GeuGQUSi+FZvjuRCUS4qslm0FMUyDb1oSuPaZo8azA9p0+QCZEUS5tgZc8G9dUOv40XeLYckikKv2Y+S7M/rlydXJ/VaHE6tfnF2fArJQ0Ke73hxEVUgg8ihOIOYmdiw3Usuc7IoMitKpwvX6UdXD10wMRTVFCoFVxtv4+tvVQ1ubNkXNOlG+Tc3WXN1lvn4bWjmyPyyenx6fIFZ0mMCMe045eZDROuuG7cph6fUb0Vww6plsdccttiZppdMdRzMlG2s/GxrA57LhHVRnTTWFhibesZ1Cch80qGjb0sh6agFHPANmeRQSmqWJOm5BSQlzZxRg2kS3pTjm+G3IrpXVfZgDw//rCH05aSGZv8qlVQQN/l+Zm+kL55VBH00rT/lqzLHb2VBDLP4s7ZoDk/G11QMAv/wN8jD5Gwp+TPnHS4nL82bysNn+Bhm7BfJKJPHQjmH2F/nHFqFdR2toQ2YN9Am2kFbaBvmPKyv0Au0C/Mueoneoj30GuY3sL5H79A+zPvoABiS3wZfV7ic4lUYuwKG5wscYwz/GqAPAmbrRwHnBN4cX1cEvMo5U7zGbVPM+LcEzM7yAt7k8aWY6b4U8DaMPQHnefwp3oGxL2DGdSDgJ/p01nue17/L9gta3Bdz+/2Jvvs/34G/HtDmlg==', 'selectors': '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'}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '7616b493c09ff73f1a25c48badeafa1330aa0fbc821a6df7f88370fa68fa1915', 'faceColors': {}, 'contentHash': '9335cb8f0ab89f4653a59de00502faba93777fd7a5f8f75509cca4e22aedd342', 'payload': 'eJylVstu00AUHTvPuumDFihvDCuIWEAasQRXKRILpCIlYm+laagUxVFCkMqK7+An+AGk8hf8RsUXcJ34zMT23My4WFU8mrlzz7lnzlzXO5kMxn7nqNs5On7n96JJNIqGF/6n9gv/Wf+5v1wNZ/3wdOB9iPrhl/NoPPNfep359OugdTrzW23PEdrn6i1GtgH1gAm8ZDKoTNmA39flwEIU52CCQLnFdWADCuvAcuCea3CwDbDXobDU5gzBf3PIZVjckZn/qsXdEHt2IkPmexaLIVMYQT4cAqcHi5DdYKxBBhiQWAT5cAh8xmwCwzmYN2SoWW/gET5Go4thND48pi6cjE/Gvel5OB7OR7I/d+fTs7BP7nttMl8ewS7u6hKjwlZaD1D4FOwTcYRMtye3oShw4QbAJeIIGbsVk8gQpw455zCv1/0cTshhh22v9v7nrx9//3x7o88as3KEQ39NQ+SylEVkFZHOYkKf13UE5z9adOnlrmMUb36KuSfJm+UY5KpJcdQjicAtsRxpsUy/JWZRcnyMKZA1cRRCz1GPRFJVWI60WKVXmVnMc3wIjilk/X4SoMYi02KdfivMokQGoDrByrJ44fjJjPMIMQ8wuI/gspA8ZXJn6bh7iMnIrfum6Q2uu5C6g9EXSdpv0KvKLXrCwuB3MHdgqibIVZPiqKdBp7TJcqTFhrAw+C1MgayJY/zoONa0QCTVFsuRFreFhcElx31wTCHXmRrdHRaZFneFhcEBqE5QGvx2MuPcRMweBjcQrAyuaCQG39WWsqHlQzrFKTm/uXtsKSsiogJ1V1PIHpd8fx1yXDvX2fLXQPZQKeJ2MiPVFFsY+AhWIioaiYgNbSmbHNvYR5zZ3JiBUUTpB32rbTD73YN1yLE+RhHlHUC3VyLi6BxpQGkj9NwVERWNRERcH5UQDVqZAo4WOLCVhEq0JCG8rhLiG6D8LS8NznslodIiSQjKzRIS3kXEDiLloaMPqcaOfE0X/83ASE35/fsHBFke6g==', 'glb': 'eNq1Vktv2kAQXvIOSdu0TdOeqmhPPTjIL9bApaS0lVIlIUqiXCIOa3tNrYKNjMlDERL/rNf+rM7aCyyGEBqpSN6dbzzzzWN3gGbr8vsSQuhTHqGvqwj9uKifPmDa7bIYVx7wDYu6fhjgCtYLKlZwkwUsonEYgcahLkDcVzC7iyPa5fZCB1KHRsCAbc/wNFUreVaZ2GWPlEzHJjbRNIfpLikVqVG0Nc9RNWqrtuMQ13GJRkqWWaaGatHywY3G49phL3CTCG0f6K/VgqqIp6HgNr0DnQEYslRgb0BSHnVYLWyFEbhdgxGDzGotXhlX4CAMGBB7jMa9iEsxDSD1GKQuo23YXCaqZcMEaHQPInie0MD3wpYLqBf8CsLbADfSiEmOds/zWHTls1tcMRTsgC/0gvTTJKZMzJGJpgubs9AP4inD4shQN/t9MO06kCGuqELihT1Afm4iQRcayghB51j3Z2IbhTGNk1O9PlALlmppKrFKmlYiRdMiyri32VcNHoe2WHoAqqZIaxKMhxDROpHf9mP/RkAax5Fv9+K0+rP6xdHlUf00See0fn5yeAzFQ0F+4PpJE3Ugg8yhOf2EmTqg7qaHOdkUlTel3YHjDOLL+w64FDWdSJ2Co03U+OpbzYATW/QGTYbR/i1M1l2f5T6+GwYZuV/UDo8PzzEvekwgl52UbN/HrO55yZgKeMyCZgwnrJdK/DZHTf7OMMtEHycz5ZsYP9u7CNdlwtvSJ52NOc7EzIQuA1lA22z03VJIJ2oOh2WakxxaWc+SpDM3h6RskBk9mCYRQzk+GXEqcnhd5xd2f//PCkJfjk7R7E+1OhRkZaqvVqftRnoJo4ztBG9GJ/PIcWXOqRyqs/lQdTrWFE8mVjYHmX/wG+RB+m4h+bPgHSwmL8w7lAfPiDHI+M+TUaaOuXIO8V/nHFqGfRWtoDVY19A62kIbaBPWPOyv0Au0Des2eoneoh30GtY3sL9H79AurLtoDxjSz5rYl4Q8xMvwbEsYri9wjDH8NUAfJMz3jxLOSbw5sS9JeFlwDvGK8B1izr8hYf4uL+F1kd8Qc9uXEt6EZ0fCeZH/EG/BsythzrUn4SfmdMZ9fmx+F54XNH8uHpv3p+bu/3wP/AUc8eyY', 'selectors': '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'}, {'kind': 'native', 'codec': 'bintools-v4', 'brep': '26411db2df8fa77051b37dfbed5925185810d476a1d9a555a0ca36ad058fdf45', 'faceColors': {}, 'contentHash': 'e1c7f4c4ad854cd0fbfa1e3cf5601b07cbe9f7185db2010ca41024fb6b7ba9b8', 'payload': 'eJylVs1u00AQXju/ddPWtED5x3CCiAOkEUdwlSJxQCpSIu5W2oZKURwlBKmceA5eghdAKm/Ba1Q8AePEM5vYM9l1sap4tTM73zcz347rHY9PR0HnsNs5PHoX9OJxPIwHF8Gn9ovgWf95sLBG0350cup9iPvRl/N4NA1eep3Z5Otp62QatNqeo9jn6i2ubB3qoeB4KUTQkbIOv6/LQYQozsEE4YeCg7EOvuRQuA4iB+m5BgdbB/s6FC61OUL43xxyEeZ3ZBq8akk3xJ6dypD5nsUSyBRGoEdCkNouImQPGHOgAwYkEYEeCUGOmA1g6IP5QIaa9QEZ4WM8vBjEo4MjmMLp+njUm5xHo8FsSPO5O5ucRX1Q32uT+PIIdn5Xl7gqLKX1AIW7YB9IImS6PbkDRYELDwApkETIOJSFQAY/3eScwrxe93M0BoUdtL3a+5+/fvz98+0NHzVplKMc+GsaPBepzD2r6OnMN/i4rqMk/YHRhZe7jlFy+CnuPUnfIscwl80KRx5JhW5J5AjGMvyWBCNxfIxbSNbEUSmeI48EpaqIHMFYhVdZMOY5PkSOK8j8eShATUQGYx1+K4KRkBFQd7CySF45QbrjPEKfB7i4j85lRTwpuLNQ3D30yZSb+6bxAucuJNcYPkmo/Qa8qpLRUxYCv4N7+6Zswlw2Kxx5GtClTZEjGBvKQuC3cAvJmjgmD8exxgJBqbZEjmDcVhYCJ457yHEFuS7k6O6IyGD0lYXAEVB3kAR+O91xbqLPLi5uoLMWuKaRCtxnU9lg+fihm4Tk9QbGXTEVX6eCGei7uoLsScH31iEnufMSW0Kma0AzlIq4ne5QNdUWLgJ01kXUNNIiNthUNiW2iY54sYExYWAsIumBH7UN4by7vw45qY+xiHQHcNrrImLrHBIgyQhn7lIRNY20iHh9dEAc0FoUqGiFDVsKqIuWBkSt64D4DdD6pkuD/V4KqGuRBkTKzRIGvIseO+hJTcc5pAc7xmu6+N8MCqlJ379/iYwfsg==', 'glb': 'eNq1Vktv2kAQXvIOSdu0TdOeqmhPPTjIb2MuJaWtlCoJURLlEnFYzJpaBRvZJg9FSPyzXvuzOmuvYTGE0EhF8u5845lvHrsDtDuX35cQQp+KCH1dRejHRf30AZMoojGuPOAbGkZe4OMKVksylnCb+jQkcRCCxiEtgHggYXoXhyRi9lwHUo+EwIAVR7UpUQ2rqZlOS7csm5qGpZV1Wy/rZdnVbMVoGoaqlW2DGi51dEN2ZYc0Hc0gmmod3CgsbjPo+60kQtcD+mu5JEv8aUi4S+5ApwOGLCUNdJCUSxxaCzpBCG7XYEQhs1qHVcYU2A98CsQuJXE/ZFJMfEg9BimipAtbi/JqaZYACe9BBM8T4ntu0GkB6vu//ODWx400YpJjs++6NLzy6C2uaBJ2wBd6YQ7SJKZM9JGJonKbs8Dz4ylDY2So6oMBmEYOZIgrMpdYYQ+QXyuRoAsNaYSgczT6mdiGQUzi5FSvD+SSJVuKbFplRSmbhm6Z0ri3+VcNFod0aHoAsiIJaxKMheDReqHX9WLvhkMSx6HX7Mdp9Wf1i6PLo/ppks5p/fzk8BiKh4I8v+UlTVSBDDKH5gwSZuKAOkoPc7IpMmtKtwfH6ceX9z1wMRTVFDoFR5uo8dW3mgYntugNmgyj/FuYvLs6y318NzRz5H5ROzw+PMes6DGBWHZScvM+pnXXTcaUw2Pqt2M4YbVcZrc5bLN3mm6b6jiZKd/E+NneBlyXCW9LnXTW5jibei60DWQ+6dLRd0spnag5HJauT3IotponSWduDomtmTN6ME3Ch3J8MvxUxPCqyi7s/v6fFYS+HJ2i2Z9qNRNEZaofCrpMHumrgr4q8OTs87FEHjGuyDmVwwz+KV/0CE8uVj4HkX/4mxFwnkXkz1nQxeSFeTN5+IwYw5z/PBnl6pgrFxD7dS6gZdhX0Qpag3UNraMttIE2YS3C/gq9QNuwbqOX6C3aQa9hfQP7e/QO7cK6i/aAIf2s8X2JyxlehmdbwHB9gWOM4a8B+iBgtn8UcEHgLfB9ScDLnDPDK9w3w4x/Q8DsXVHA6zy/DDPblwLehGdHwEWef4a34NkVMOPaE/ATczrjPj82vwvPC3piLh6Z96fm7v98D/wFWaDxZQ==', 'selectors': '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'}]


def seed_result(
    document: Path | str,
    descriptor: Mapping[str, Any] | None = None,
    *,
    model: Path | str | None = None,
    parts: bool = True,
    components: tuple[str, ...] = ("c0",),
    kind: str = "assembly-package",
    entry_kind: str = "part",
    sidecar: Mapping[str, Any] | None = None,
    tokenize: bool = True,
) -> str:
    """Seed geometry and, unless ``parts`` is False, each component's part as a build
    derives it under FIXTURE_PRODUCER (its display mesh, selector table and
    record), without native imports.

    Caller aliases are remapped to genuine geometry CIDs. Explicit malformed
    structure/geometry overrides stay malformed so completeness checks can reject them;
    ``tokenize=False`` keeps a caller's provisional ids too (a malformed tree).
    """
    import base64
    import copy
    import zlib
    from cadgen._internal.component_package import canonical_json_bytes
    from cadgen.store.meshes import body_facts
    from cadgen.store.objects import put_object
    from cadgen.store.parts import _write, part_key
    from cadgen.store.records import note_document_tree, note_output, write_record
    from cadgen.store.results import producer_versions
    from cadgen.store.trees import TREE_KIND, TREE_SCHEMA, tree_kind

    def inflate(text: str) -> bytes:
        return zlib.decompress(base64.b64decode(text))

    document = Path(document)
    descriptor = copy.deepcopy(dict(descriptor or {}))
    raw_components = descriptor.get("components")
    if not isinstance(raw_components, dict):
        raw_components = {cid: {} for cid in components}
    if len(raw_components) > len(_GEOMETRY_FIXTURES):
        raise ValueError("seed_result supports at most four independent fixture components")
    tree_components, aliases, component_colors = {}, {}, {}
    for index, (alias, raw_entry) in enumerate(raw_components.items()):
        fixture = _GEOMETRY_FIXTURES[index]
        entry = {name: copy.deepcopy(fixture[name])
                 for name in ("kind", "codec", "brep", "faceColors", "contentHash")}
        put_object(inflate(fixture["payload"]))
        if parts:
            key, glb = part_key(entry, FIXTURE_PRODUCER), inflate(fixture["glb"])
            if body_facts(glb)["part"] != key:
                raise ValueError("a seeded part's mesh names another part: derive the fixture parts again")
            _write(key, glb, inflate(fixture["selectors"]))
        raw_entry = dict(raw_entry or {})
        if raw_entry.get("color") is not None:
            entry["color"] = raw_entry["color"]
            component_colors[alias] = raw_entry["color"]
        if "brepObject" in raw_entry:
            entry["brep"] = raw_entry["brepObject"]
        cid = entry["contentHash"][:16]
        aliases[alias] = cid
        tree_components[cid] = entry
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    occurrences = descriptor.get("occurrences")
    if not isinstance(occurrences, list):
        occurrences = [{"id": f"o1.{i}" if len(aliases) > 1 else "o1", "name": alias,
                        "component": cid, "transform": identity}
                       for i, (alias, cid) in enumerate(aliases.items(), 1)]
    else:
        for occurrence in occurrences:
            occurrence["component"] = aliases.get(occurrence.get("component"), occurrence.get("component"))
    children = [{"id": occurrence["id"], "name": occurrence.get("name", occurrence["id"]),
                 "nodeType": "part", "children": []} for occurrence in occurrences]
    assembly = descriptor.get("assembly")
    if not isinstance(assembly, dict):
        root = children[0] if len(children) == 1 and children[0]["id"] == "o1" else {
            "id": "o1", "name": descriptor.get("label") or "model", "nodeType": "assembly", "children": children}
        assembly = {"root": root}
    tree = {"kind": TREE_KIND, "schemaVersion": TREE_SCHEMA,
            "label": descriptor.get("label") or "model", "units": "mm",
            "components": tree_components, "occurrences": occurrences, "links": [],
            "assembly": assembly, "stats": {"occurrenceCount": len(occurrences), "linkCount": 0}}
    # The ids above are provisional: the tree names its nodes by tokens minted
    # from its structure, as a build does. Callers read them off the tree
    # (tests.python.support.tree_ids).
    if tokenize and isinstance(tree["assembly"].get("root"), dict) and "id" in tree["assembly"]["root"]:
        from cadgen._internal.tree_tokens import assign_tokens, retoken
        tree = retoken(tree, assign_tokens(tree["assembly"]["root"], occurrences, [], label=tree["label"]))
    tree["entryKind"] = tree_kind(tree)
    if descriptor.get("kind") not in (None, kind):
        tree["kind"] = descriptor["kind"]
    for key in ("bbox", "capabilities", "edgeRendering", "color"):
        if key in descriptor:
            tree[key] = descriptor[key]
    # Deliberately malformed fixture knobs must remain malformed; production
    # publication goes through put_tree and native preparation instead.
    tree_hash = put_object(canonical_json_bytes(tree))
    try:
        sha = hashlib.sha256(document.read_bytes()).hexdigest()
    except OSError:
        sha = ""
    owner = Path(model) if model is not None else document
    record = {"entryKind": tree["entryKind"], "sourceKind": "python" if model is not None else "step",
              "tree": tree_hash, "closure": {"hash": sha, "files": [], "static": True}, "children": [],
              "outputs": {str(document.resolve()): {"sha256": sha}}, "producer": producer_versions()}
    if sidecar:
        record.update(sidecar)
    write_record(owner, record)
    if sha:
        note_document_tree(sha, tree_hash, kind="step", producer=FIXTURE_PRODUCER)
    if model is not None:
        note_output(document, owner)
    return tree_hash
